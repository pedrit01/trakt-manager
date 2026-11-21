# Proposal

## Why

Trakt ha cambiado la forma de registrar aplicaciones: las nuevas **ya no reciben Client Secret por defecto**. Lo considera obsoleto para el inicio de sesión de usuarios y solo lo concede, tras revisión manual, para intercambios entre servidores (developer.trakt.tv, guías "Create an app" y "OAuth", noviembre de 2026). trakt-manager exige el Client Secret en el asistente, en el device flow y en la renovación del token, así que con una aplicación nueva de Trakt no se puede configurar ni iniciar sesión.

## What Changes

- El Client Secret pasa a ser **opcional** en toda la aplicación. Si existe, se sigue enviando como hasta ahora (compatibilidad con aplicaciones antiguas). Si no existe, el device flow, la renovación y la revocación del token se hacen solo con el Client ID.
- El modo configuración deja de exigir `TRAKT_CLIENT_SECRET`: basta con `TRAKT_CLIENT_ID` y `API_KEY`.
- El asistente y los ajustes de la GUI muestran el Client Secret como campo opcional. Indican que las aplicaciones nuevas de Trakt no lo tienen y que la Redirect URI no la usa el device flow (Trakt desaconseja `urn:ietf:wg:oauth:2.0:oob`).
- Si Trakt rechaza el device flow o la renovación por falta de secreto, el error lo dice claramente, en lugar de "Fallo inesperado (HTTP 401)".

No se sabe aún si Trakt acepta el device flow sin secreto: la documentación lo describe sin aclarar ese punto. Este cambio lo permite y la prueba en vivo con una aplicación real lo confirma. Si Trakt lo rechazara, la alternativa es el flujo PKCE (cambio aparte).

## Capabilities

### New Capabilities
<!-- Ninguna. -->

### Modified Capabilities
- `trakt-auth`: el Client Secret es opcional; la autorización, la renovación y la revocación funcionan sin él.
- `runtime-settings`: el modo configuración y el asistente solo exigen el Client ID (además de la `API_KEY`).

## Impact

- **Dependencia previa**: los specs `trakt-auth` y `runtime-settings` vienen de `dockerize-trakt-manager` y `add-web-gui`, que deben archivarse antes que este.
- **Código**: `auth.py`, `app_context.py`, `settings_store.py`, `config.py`, `api.py` y la GUI (`views/setup.js`, `views/settings.js`), además de sus tests.
- **Documentación**: `README.md`, `.env.example` y `CLAUDE.md`.
- **Compatibilidad**: quien ya tenga un Client Secret no nota ningún cambio.
