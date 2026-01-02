from cartesia import AsyncCartesia
import voluptuous as vol
import os
import json
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.httpx_client import get_async_client
from .const import VOICES_CACHE_FILE

async def get_all_voices(hass: HomeAssistant, api_key: str):
    """Stáhne a nacachuje hlasy."""
    cache_file = os.path.join(hass.config.config_dir, VOICES_CACHE_FILE)
    
    # Zkusíme načíst z cache
    if os.path.exists(cache_file):
        try:
            def _read_cache():
                with open(cache_file, "r") as f:
                    return json.load(f)
            
            cache = await hass.async_add_executor_job(_read_cache)
            if cache.get("api_key") == api_key:
                return cache.get("voices", [])
        except:
            pass
    
    # Stáhneme z API
    httpx_client = get_async_client(hass)
    try:
        client = AsyncCartesia(api_key=api_key, httpx_client=httpx_client)
        voices_pager = await client.voices.list()
        voices = [v async for v in voices_pager]
    except Exception:
        return []
    
    voices_list = []
    for v in voices:
        voices_list.append({
            "id": getattr(v, 'id'),
            "name": getattr(v, 'name'),
            "language": getattr(v, 'language', []),
            "is_custom": getattr(v, 'is_custom', False),
            "mode": getattr(v, 'mode', ""),
        })
    
    # Uložíme do cache
    try:
        def _write_cache():
            with open(cache_file, "w") as f:
                json.dump({"api_key": api_key, "voices": voices_list}, f)
        
        await hass.async_add_executor_job(_write_cache)
    except:
        pass
    
    return voices_list

def _get_form_options(voices):
    """Pomocná funkce pro přípravu dat do formulářů."""
    languages = sorted(set(lang for v in voices for lang in (v["language"] if isinstance(v["language"], list) else [v["language"]])))
    voices_options = {v["id"]: f"{v['name']} ({v['mode']})" for v in voices}
    
    default_lang = "cs" if "cs" in languages else (languages[0] if languages else "")
    default_voice = None
    if voices_options:
        # Zkusíme najít hlas pro defaultní jazyk
        default_voice = next((v["id"] for v in voices if default_lang in (v["language"] if isinstance(v["language"], list) else [v["language"]])), list(voices_options.keys())[0])

    return languages, voices_options, default_lang, default_voice


class CartesiaTTSConfigFlow(config_entries.ConfigFlow, domain="cartesia_tts"):
    """Handle a config flow for Cartesia TTS."""
    VERSION = 1

    def __init__(self):
        self.api_key = None
        self.voices = []

    async def async_step_user(self, user_input=None):
        """Krok 1: Inicializace. Zkontroluje, zda už existuje jiná konfigurace."""
        
        # 1. Zkontrolujeme, jestli už máme nějakou instanci této integrace
        existing_entries = self._async_current_entries()
        
        if existing_entries:
            # Pokud už existuje, vezmeme API klíč z té první.
            self.api_key = existing_entries[0].data[CONF_API_KEY]
            
            # Rovnou stáhneme hlasy (ověření klíče proběhne tímto)
            self.voices = await get_all_voices(self.hass, self.api_key)
            if not self.voices:
                 return self.async_abort(reason="cannot_connect")
            
            # Přeskočíme zadávání klíče a jdeme rovnou na nastavení hlasu
            return await self.async_step_settings()

        # 2. Pokud je to úplně první instalace, zeptáme se na API klíč
        errors = {}
        if user_input is not None:
            self.api_key = user_input[CONF_API_KEY]
            try:
                self.voices = await get_all_voices(self.hass, self.api_key)
                if not self.voices:
                    raise ValueError("No voices found")
                return await self.async_step_settings()
            except Exception:
                errors[CONF_API_KEY] = "invalid_api_key"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY): str,
            }),
            errors=errors,
        )

    async def async_step_settings(self, user_input=None):
        """Krok 2: Nastavení konkrétní entity (Jméno, Hlas, Jazyk)."""
        
        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get("name", "Cartesia TTS"),
                data={
                    CONF_API_KEY: self.api_key,
                    "name": user_input["name"],
                    "language": user_input["language"],
                    "voice": user_input["voice"],
                    "speed": user_input["speed"],
                },
            )

        languages, voices_options, default_lang, default_voice = _get_form_options(self.voices)
        
        existing_count = len(self._async_current_entries())
        default_name = f"Cartesia {existing_count + 1}"

        safe_default_voice = default_voice if default_voice else (list(voices_options.keys())[0] if voices_options else "")

        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema({
                vol.Optional("name", default=default_name): str,
                vol.Optional("language", default=default_lang): vol.In(languages),
                vol.Optional("voice", default=safe_default_voice): vol.In(voices_options),
                vol.Optional("speed", default=1.0): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=2.0)),
            }),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Umožní upravit existující entitu (změnit hlas)."""
        # OPRAVA: Nepředáváme config_entry jako argument, OptionsFlow si ho vezme sám
        return CartesiaTTSOptionsFlow()


class CartesiaTTSOptionsFlow(config_entries.OptionsFlow):
    """Konfigurace (úprava) již existující entity."""
    
    # OPRAVA: Odstraněn __init__, self.config_entry je nyní property v rodičovské třídě

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            new_data = self.config_entry.data.copy()
            new_data.update(user_input)
            self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
            
            # Je nutné reloadovat entry, aby se změny projevily hned
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            
            return self.async_create_entry(title="", data={})

        api_key = self.config_entry.data[CONF_API_KEY]
        voices = await get_all_voices(self.hass, api_key)
        languages, voices_options, _, _ = _get_form_options(voices)

        current_data = self.config_entry.data

        current_voice = current_data.get("voice")
        if current_voice not in voices_options and voices_options:
            current_voice = list(voices_options.keys())[0]

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional("name", default=current_data.get("name")): str,
                vol.Optional("language", default=current_data.get("language")): vol.In(languages),
                vol.Optional("voice", default=current_voice): vol.In(voices_options),
                vol.Optional("speed", default=current_data.get("speed", 1.0)): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=2.0)),
            }),
        )