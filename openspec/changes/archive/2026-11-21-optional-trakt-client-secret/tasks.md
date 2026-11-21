# Tasks

> Criterio común a todas las tareas de implementación: una tarea solo está terminada si su código es legible y está documentado (docstrings en español, type hints en todas las firmas y comentarios que explican el porqué de lo no obvio). Ninguna tarea hace commit ni push.

## 1. Núcleo

- [x] 1.1 Hacer opcional el Client Secret en `auth.py` (device flow, renovación y revocación solo lo envían si existe; error claro si Trakt rechaza el cliente sin secreto) y en `app_context.py`; verificar con tests de device flow, renovación y revocación con y sin secreto (comprobando el cuerpo enviado)
- [x] 1.2 Quitar `TRAKT_CLIENT_SECRET` de lo exigido para salir del modo configuración (`settings_store.py`) y del asistente (`complete_setup`); verificar con tests de modo configuración y asistente sin secreto

## 2. GUI y documentación

- [x] 2.1 Marcar el Client Secret como opcional en el asistente y en los ajustes, explicar que las aplicaciones nuevas de Trakt no lo tienen y que el device flow no usa la Redirect URI; verificar en el navegador con la demo
- [x] 2.2 Actualizar `README.md`, `.env.example` y `CLAUDE.md`; verificar que no queda ninguna instrucción que exija el Client Secret

## 3. Verificación real

- [x] 3.1 Reconstruir el contenedor local y, con una aplicación real de Trakt sin secreto, comprobar desde la GUI que el device flow funciona (o, si Trakt lo rechaza, que el error lo explica); verificar con `pytest` completo y `openspec validate optional-trakt-client-secret --strict`

## Workflow follow-up

- Archivar después de `dockerize-trakt-manager` y `add-web-gui`.
