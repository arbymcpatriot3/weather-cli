#!/usr/bin/env python3
"""
core/i18n/strings.py — CleanShot HQ Complete Bilingual String Dictionary
Every user-facing string in the program, in English and Spanish.
This is the source of truth for display-layer translations.

Language state is shared with core.i18n.translator so a single
set_language() call (from either module) affects both.

Usage:
    from core.i18n.strings import t, set_language, get_language
    set_language('es')
    print(t('current_conditions'))  # -> "Condiciones Actuales"
"""

STRINGS = {

    # ── MENU ──────────────────────────────────────────────────────
    'menu_title':           {'en': 'What would you like to do?',
                             'es': '¿Qué desea hacer?'},
    'menu_refresh':         {'en': 'Refresh weather report',
                             'es': 'Actualizar reporte del tiempo'},
    'menu_summary':         {'en': 'Simple one-line summary',
                             'es': 'Resumen de una línea'},
    'menu_compact':         {'en': 'Compact view',
                             'es': 'Vista compacta'},
    'menu_alerts':          {'en': 'Active weather alerts',
                             'es': 'Alertas meteorológicas activas'},
    'menu_route':           {'en': 'Route weather  (enter two cities)',
                             'es': 'Tiempo en ruta  (ingrese dos ciudades)'},
    'menu_map':             {'en': 'Regional map',
                             'es': 'Mapa regional'},
    'menu_settings':        {'en': 'Settings',
                             'es': 'Configuración'},
    'menu_doctor':          {'en': 'Doctor  (system health check)',
                             'es': 'Doctor  (diagnóstico del sistema)'},
    'menu_help':            {'en': 'Help',
                             'es': 'Ayuda'},
    'menu_continuous':      {'en': 'Continuous Monitor  (auto-refresh)',
                             'es': 'Monitor continuo  (actualización automática)'},
    'menu_flyer':           {'en': 'View Flyer / Share info',
                             'es': 'Ver folleto / Compartir info'},
    'menu_language':        {'en': 'Language / Idioma  (English / Español)',
                             'es': 'Idioma / Language  (Español / English)'},
    'menu_glossary':        {'en': 'Help & icon glossary',
                             'es': 'Ayuda y glosario de iconos'},
    'menu_exit':            {'en': 'Exit',
                             'es': 'Salir'},
    'menu_prompt':          {'en': 'Choice (or Enter to refresh):',
                             'es': 'Opción (o Enter para actualizar):'},

    # ── SECTION HEADERS ───────────────────────────────────────────
    'current_conditions':   {'en': 'Current Conditions',
                             'es': 'Condiciones Actuales'},
    'hourly_forecast':      {'en': 'Hourly Forecast (Next 24 hours)',
                             'es': 'Pronóstico por Hora (Próximas 24 horas)'},
    'seven_day_forecast':   {'en': '7-Day Forecast',
                             'es': 'Pronóstico de 7 Días'},
    'parking_runway':       {'en': 'Parking Runway',
                             'es': 'Corredor de Estacionamiento'},
    'hos_status':           {'en': 'HOS STATUS  (Advisory Only — Not an ELD)',
                             'es': 'ESTADO HOS  (Solo Informativo — No es un ELD)'},
    'hazard_report':        {'en': 'Road Hazard Report',
                             'es': 'Reporte de Peligros Viales'},

    # ── DATA LABELS ───────────────────────────────────────────────
    'location':             {'en': 'Location',         'es': 'Ubicación'},
    'updated':              {'en': 'Updated',          'es': 'Actualizado'},
    'temperature':          {'en': 'Temperature',      'es': 'Temperatura'},
    'condition':            {'en': 'Condition',        'es': 'Condición'},
    'humidity':             {'en': 'Humidity',         'es': 'Humedad'},
    'wind':                 {'en': 'Wind',             'es': 'Viento'},
    'sunrise_sunset':       {'en': 'Sunrise / Sunset', 'es': 'Amanecer / Atardecer'},
    'high':                 {'en': 'High',             'es': 'Máx'},
    'low':                  {'en': 'Low',              'es': 'Mín'},
    'rain':                 {'en': 'Rain',             'es': 'Lluvia'},
    'gust':                 {'en': 'Gust',             'es': 'Ráfaga'},
    'away':                 {'en': 'away',             'es': 'de distancia'},
    'stops_in_corridor':    {'en': 'stops in corridor','es': 'paradas en el corredor'},
    'runway':               {'en': 'Runway',           'es': 'Corredor'},
    'feels_like':           {'en': 'feels like',       'es': 'sensación térmica'},
    'calm':                 {'en': 'Calm',             'es': 'Calmo'},

    # ── HOS LABELS ────────────────────────────────────────────────
    'drive_remaining':      {'en': 'Drive remaining',
                             'es': 'Tiempo de manejo restante'},
    'duty_window_left':     {'en': 'Duty window left',
                             'es': 'Ventana de servicio restante'},
    'effective_limit':      {'en': 'Effective limit',
                             'es': 'Límite efectivo'},
    'next_break':           {'en': "Next break req'd in",
                             'es': 'Próximo descanso en'},
    'weekly':               {'en': 'Weekly (70h/8-day)',
                             'es': 'Semanal (70h/8 días)'},
    'status':               {'en': 'Status',           'es': 'Estado'},
    'off_duty':             {'en': 'Off Duty',         'es': 'Fuera de Servicio'},
    'on_duty_nd':           {'en': 'On Duty (Not Driving)', 'es': 'En Servicio (Sin Conducir)'},
    'driving':              {'en': 'Driving',          'es': 'Conduciendo'},
    'sleeper':              {'en': 'Sleeper Berth',    'es': 'Litera'},
    'of_driving':           {'en': 'of driving',       'es': 'de conducción'},
    'of_11h':               {'en': 'of 11h',           'es': 'de 11h'},
    'of_14h':               {'en': 'of 14h',           'es': 'de 14h'},

    # ── STATUS MESSAGES ───────────────────────────────────────────
    'road_clear_title':     {'en': "You've got a clean shot, good buddy!",
                             'es': '¡Tienes vía libre, compañero!'},
    'road_clear_sub':       {'en': 'Road is clear — keep the shiny side up.',
                             'es': 'Carretera despejada — ¡que rueden los kilómetros!'},
    'starting_up':          {'en': 'CleanShot HQ starting up...',
                             'es': 'CleanShot HQ iniciando...'},
    'loading_weather':      {'en': 'Loading weather data...',
                             'es': 'Cargando datos del tiempo...'},
    'no_data':              {'en': 'No data available',
                             'es': 'Datos no disponibles'},
    'error_connecting':     {'en': 'Error connecting to server',
                             'es': 'Error al conectar con el servidor'},

    # ── HAZARD TYPES ──────────────────────────────────────────────
    'black_ice':            {'en': 'Black Ice Risk',    'es': 'Riesgo de Hielo Negro'},
    'bridge_freeze':        {'en': 'Bridge Freeze',     'es': 'Puente Congelado'},
    'fog_advisory':         {'en': 'Fog Advisory',      'es': 'Aviso de Niebla'},
    'flood_risk':           {'en': 'Flood Risk',        'es': 'Riesgo de Inundación'},
    'diesel_gel':           {'en': 'Diesel Gel Risk',   'es': 'Riesgo de Gelificación de Diésel'},
    'high_wind':            {'en': 'High Wind Advisory','es': 'Aviso de Vientos Fuertes'},
    'mudslide':             {'en': 'Mudslide Risk',     'es': 'Riesgo de Deslizamiento'},

    # ── WEATHER CONDITIONS ────────────────────────────────────────
    'clear_sky':            {'en': 'Clear sky',         'es': 'Cielo despejado'},
    'mainly_clear':         {'en': 'Mainly clear',      'es': 'Mayormente despejado'},
    'partly_cloudy':        {'en': 'Partly cloudy',     'es': 'Parcialmente nublado'},
    'overcast':             {'en': 'Overcast',          'es': 'Nublado'},
    'fog':                  {'en': 'Fog',               'es': 'Niebla'},
    'icy_fog':              {'en': 'Icy fog',           'es': 'Niebla helada'},
    'light_drizzle':        {'en': 'Light drizzle',     'es': 'Llovizna ligera'},
    'drizzle':              {'en': 'Drizzle',           'es': 'Llovizna'},
    'heavy_drizzle':        {'en': 'Heavy drizzle',     'es': 'Llovizna intensa'},
    'freezing_drizzle':     {'en': 'Freezing drizzle',  'es': 'Llovizna helada'},
    'heavy_freezing_drizzle':{'en': 'Heavy freezing drizzle', 'es': 'Llovizna helada intensa'},
    'slight_rain':          {'en': 'Slight rain',       'es': 'Lluvia ligera'},
    'moderate_rain':        {'en': 'Moderate rain',     'es': 'Lluvia moderada'},
    'heavy_rain':           {'en': 'Heavy rain',        'es': 'Lluvia intensa'},
    'light_rain':           {'en': 'Light rain',        'es': 'Lluvia ligera'},
    'snow':                 {'en': 'Snow',              'es': 'Nieve'},
    'light_snow':           {'en': 'Light snow',        'es': 'Nevada ligera'},
    'heavy_snow':           {'en': 'Heavy snow',        'es': 'Nevada intensa'},
    'slight_snow':          {'en': 'Slight snow',       'es': 'Nevada ligera'},
    'snow_grains':          {'en': 'Snow grains',       'es': 'Gránulos de nieve'},
    'rain_showers':         {'en': 'Rain showers',      'es': 'Chubascos'},
    'moderate_showers':     {'en': 'Moderate showers',  'es': 'Chubascos moderados'},
    'violent_showers':      {'en': 'Violent showers',   'es': 'Chubascos violentos'},
    'snow_showers':         {'en': 'Snow showers',      'es': 'Aguanieve'},
    'heavy_snow_showers':   {'en': 'Heavy snow showers','es': 'Aguanieve intensa'},
    'thunderstorm':         {'en': 'Thunderstorm',      'es': 'Tormenta eléctrica'},
    'thunderstorm_hail':    {'en': 'Thunderstorm w/ hail', 'es': 'Tormenta con granizo'},
    'windy':                {'en': 'Windy',             'es': 'Ventoso'},
    'blizzard':             {'en': 'Blizzard',          'es': 'Ventisca'},
    'freezing_rain':        {'en': 'Freezing rain',     'es': 'Lluvia helada'},
    'sleet':                {'en': 'Sleet',             'es': 'Aguanieve'},

    # ── DAYS OF WEEK ──────────────────────────────────────────────
    'mon':                  {'en': 'Mon', 'es': 'Lun'},
    'tue':                  {'en': 'Tue', 'es': 'Mar'},
    'wed':                  {'en': 'Wed', 'es': 'Mié'},
    'thu':                  {'en': 'Thu', 'es': 'Jue'},
    'fri':                  {'en': 'Fri', 'es': 'Vie'},
    'sat':                  {'en': 'Sat', 'es': 'Sáb'},
    'sun':                  {'en': 'Sun', 'es': 'Dom'},
    'monday':               {'en': 'Monday',    'es': 'Lunes'},
    'tuesday':              {'en': 'Tuesday',   'es': 'Martes'},
    'wednesday':            {'en': 'Wednesday', 'es': 'Miércoles'},
    'thursday':             {'en': 'Thursday',  'es': 'Jueves'},
    'friday':               {'en': 'Friday',    'es': 'Viernes'},
    'saturday':             {'en': 'Saturday',  'es': 'Sábado'},
    'sunday':               {'en': 'Sunday',    'es': 'Domingo'},

    # ── MONTHS ────────────────────────────────────────────────────
    'jan':  {'en': 'Jan', 'es': 'Ene'},
    'feb':  {'en': 'Feb', 'es': 'Feb'},
    'mar':  {'en': 'Mar', 'es': 'Mar'},
    'apr':  {'en': 'Apr', 'es': 'Abr'},
    'may':  {'en': 'May', 'es': 'May'},
    'jun':  {'en': 'Jun', 'es': 'Jun'},
    'jul':  {'en': 'Jul', 'es': 'Jul'},
    'aug':  {'en': 'Aug', 'es': 'Ago'},
    'sep':  {'en': 'Sep', 'es': 'Sep'},
    'oct':  {'en': 'Oct', 'es': 'Oct'},
    'nov':  {'en': 'Nov', 'es': 'Nov'},
    'dec':  {'en': 'Dec', 'es': 'Dic'},

    # ── TTS VOICE ALERTS ──────────────────────────────────────────
    'tts_welcome':          {'en': 'Welcome to CleanShot HQ. Road intelligence for truckers.',
                             'es': 'Bienvenido a CleanShot HQ. Inteligencia vial para camioneros.'},
    'tts_road_clear':       {'en': 'Road is clear. Keep the shiny side up.',
                             'es': 'Carretera despejada. Buen viaje, compañero.'},
    'tts_black_ice':        {'en': 'Warning: black ice risk ahead. Reduce speed.',
                             'es': 'Advertencia: riesgo de hielo negro adelante. Reduzca velocidad.'},
    'tts_bridge_freeze':    {'en': 'Warning: bridge freeze ahead. Use caution.',
                             'es': 'Advertencia: puente congelado adelante. Tome precauciones.'},
    'tts_fog':              {'en': 'Fog advisory. Reduce speed and use low beams.',
                             'es': 'Aviso de niebla. Reduzca velocidad y use luces bajas.'},
    'tts_flood':            {'en': 'Flood risk on route. Do not drive through water.',
                             'es': 'Riesgo de inundación en ruta. No cruce el agua.'},
    'tts_high_wind':        {'en': 'High wind advisory. Grip the wheel firmly.',
                             'es': 'Aviso de vientos fuertes. Sujete el volante firmemente.'},
    'tts_diesel_gel':       {'en': 'Diesel gel risk. Use anti-gel additive.',
                             'es': 'Riesgo de gelificación de diésel. Use aditivo antigel.'},
    'tts_hos_warning':      {'en': 'HOS warning: less than 2 hours of drive time remaining.',
                             'es': 'Aviso HOS: menos de 2 horas de manejo restantes.'},
    'tts_hos_critical':     {'en': 'HOS critical: less than 30 minutes of drive time remaining.',
                             'es': 'HOS crítico: menos de 30 minutos de manejo restantes.'},

    # ── LANGUAGE SELECTION ────────────────────────────────────────
    'select_language':      {'en': 'Select Language',  'es': 'Seleccionar Idioma'},
    'english':              {'en': 'English',          'es': 'Inglés'},
    'spanish':              {'en': 'Spanish',          'es': 'Español'},
    'language_saved':       {'en': 'Language saved.',  'es': 'Idioma guardado.'},

    # ── CONTINUOUS MODE ───────────────────────────────────────────
    'continuous_header':    {'en': 'CONTINUOUS MODE — Press Q to quit',
                             'es': 'MODO CONTINUO — Presione Q para salir'},
    'next_refresh':         {'en': 'Next refresh in',  'es': 'Próxima actualización en'},
    'gps_auto_mode':        {'en': 'GPS auto mode',    'es': 'Modo automático GPS'},
    'parked':               {'en': 'Parked',           'es': 'Estacionado'},

    # ── SETTINGS ──────────────────────────────────────────────────
    'settings_title':       {'en': 'Settings',         'es': 'Configuración'},
    'units_imperial':       {'en': 'Imperial (°F, mph)','es': 'Imperial (°F, mph)'},
    'units_metric':         {'en': 'Metric (°C, km/h)','es': 'Métrico (°C, km/h)'},

    # ── GLOSSARY ──────────────────────────────────────────────────
    'glossary_title':       {'en': 'Icon & Symbol Glossary',
                             'es': 'Glosario de Iconos y Símbolos'},
    'press_any_key':        {'en': 'Press any key to continue...',
                             'es': 'Presione cualquier tecla para continuar...'},
    'return_to_menu':       {'en': 'Press Q to return to menu',
                             'es': 'Presione Q para volver al menú'},

    # ── MISC DISPLAY ──────────────────────────────────────────────
    'rain_probability':     {'en': 'Rain Probability (Next 12 hours)',
                             'es': 'Probabilidad de Lluvia (Próximas 12 horas)'},
    'regional_overview':    {'en': 'Regional Weather Overview',
                             'es': 'Resumen Meteorológico Regional'},
    'remaining':            {'en': 'remaining',        'es': 'restante'},
    'more_stops':           {'en': 'more stops in range',
                             'es': 'paradas más en ruta'},
    'referral_line1':       {'en': 'Refer a friend → earn $1/mo off your subscription.',
                             'es': 'Refiere un amigo → gana $1/mes de descuento.'},
    'referral_line2':       {'en': 'Share:',           'es': 'Comparte:'},
}


# ── Language state ─────────────────────────────────────────────────────────────
# strings.py delegates language state to translator.py so a single
# set_language() call from either module keeps them in sync.

def get_language() -> str:
    """Return current language code, delegating to translator for single source of truth."""
    try:
        from core.i18n.translator import current_language
        return current_language()
    except Exception:
        return 'en'


def set_language(lang: str) -> None:
    """Set language in both strings.py and translator.py."""
    if lang not in ('en', 'es'):
        return
    try:
        from core.i18n.translator import set_language as _tset
        _tset(lang)
    except Exception:
        pass


def t(key: str, lang: str = None) -> str:
    """
    Translate a key to the current language.
    Falls back to English if key or translation missing. Never crashes.

    Usage:
        t('current_conditions')        # uses current language
        t('current_conditions', 'es')  # force Spanish
    """
    use_lang = lang or get_language()
    entry = STRINGS.get(key)
    if not entry:
        return key
    return entry.get(use_lang) or entry.get('en') or key


# ── Weather condition translation ──────────────────────────────────────────────

# Maps every Open-Meteo WEATHER_CODES description to its strings.py key
_CONDITION_MAP = {
    'clear sky':                  'clear_sky',
    'mainly clear':               'mainly_clear',
    'partly cloudy':              'partly_cloudy',
    'overcast':                   'overcast',
    'fog':                        'fog',
    'icy fog':                    'icy_fog',
    'light drizzle':              'light_drizzle',
    'drizzle':                    'drizzle',
    'heavy drizzle':              'heavy_drizzle',
    'freezing drizzle':           'freezing_drizzle',
    'heavy freezing drizzle':     'heavy_freezing_drizzle',
    'slight rain':                'slight_rain',
    'rain':                       'moderate_rain',
    'heavy rain':                 'heavy_rain',
    'freezing rain':              'freezing_rain',
    'heavy freezing rain':        'heavy_rain',
    'slight snow':                'slight_snow',
    'snow':                       'snow',
    'heavy snow':                 'heavy_snow',
    'snow grains':                'snow_grains',
    'rain showers':               'rain_showers',
    'moderate showers':           'moderate_showers',
    'violent showers':            'violent_showers',
    'snow showers':               'snow_showers',
    'heavy snow showers':         'heavy_snow_showers',
    'thunderstorm':               'thunderstorm',
    'thunderstorm w/ hail':       'thunderstorm_hail',
    'windy':                      'windy',
    'blizzard':                   'blizzard',
    'sleet':                      'sleet',
}


def translate_weather_condition(condition: str, lang: str = None) -> str:
    """
    Translate a weather condition string (without emoji).
    Returns original string unchanged when language is English or key not found.
    """
    use_lang = lang or get_language()
    if use_lang == 'en':
        return condition
    key = _CONDITION_MAP.get(condition.lower().strip())
    if key:
        return t(key, use_lang)
    return condition


def translate_weather_desc(desc_short: str, lang: str = None) -> str:
    """
    Translate a full desc_short string like "Clear sky ☀" → "Cielo despejado ☀".
    Handles the trailing emoji by splitting on the last space.
    """
    use_lang = lang or get_language()
    if use_lang == 'en':
        return desc_short
    # desc_short format: "Text description emoji"
    # Split off the last token (emoji) for translation
    parts = desc_short.rsplit(' ', 1)
    if len(parts) == 2:
        translated = translate_weather_condition(parts[0], use_lang)
        return f"{translated} {parts[1]}"
    return translate_weather_condition(desc_short, use_lang)


# ── Day / month translation ────────────────────────────────────────────────────

_DAY_MAP = {
    'mon': 'mon', 'tue': 'tue', 'wed': 'wed',
    'thu': 'thu', 'fri': 'fri', 'sat': 'sat', 'sun': 'sun',
}

_MONTH_MAP = {
    'jan': 'jan', 'feb': 'feb', 'mar': 'mar', 'apr': 'apr',
    'may': 'may', 'jun': 'jun', 'jul': 'jul', 'aug': 'aug',
    'sep': 'sep', 'oct': 'oct', 'nov': 'nov', 'dec': 'dec',
}


def translate_day(day_abbr: str, lang: str = None) -> str:
    """Translate a 3-letter day abbreviation. 'Mon' -> 'Lun'"""
    use_lang = lang or get_language()
    if use_lang == 'en':
        return day_abbr
    key = _DAY_MAP.get(day_abbr.lower()[:3])
    return t(key, use_lang) if key else day_abbr


def translate_month(month_abbr: str, lang: str = None) -> str:
    """Translate a 3-letter month abbreviation. 'Jun' -> 'Jun' (same), 'Aug' -> 'Ago'"""
    use_lang = lang or get_language()
    if use_lang == 'en':
        return month_abbr
    key = _MONTH_MAP.get(month_abbr.lower()[:3])
    return t(key, use_lang) if key else month_abbr


def translate_day_label(label: str, lang: str = None) -> str:
    """
    Translate a day label in 'Mon Jun 01' format.
    Returns translated label in same format, e.g. 'Lun Jun 01'.
    """
    use_lang = lang or get_language()
    if use_lang == 'en':
        return label
    parts = label.split(' ')
    if len(parts) >= 3:
        return f"{translate_day(parts[0], use_lang)} {translate_month(parts[1], use_lang)} {parts[2]}"
    if len(parts) == 2:
        return f"{translate_day(parts[0], use_lang)} {translate_month(parts[1], use_lang)}"
    if len(parts) == 1:
        return translate_day(parts[0], use_lang)
    return label
