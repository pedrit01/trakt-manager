# Spec Delta

## MODIFIED Requirements

### Requirement: Modo configuración
Si falta el Client ID de Trakt o la `API_KEY`, el servicio SHALL arrancar en modo configuración; el Client Secret es opcional y su ausencia no activa ese modo. En modo configuración solo responden `/health`, la GUI y las rutas del asistente; el resto de rutas MUST responder 503 indicando qué falta.

#### Scenario: Primer arranque sin configuración
- **WHEN** se arranca la imagen sin `.env` ni configuración guardada
- **THEN** el servicio arranca, `GET /health` responde 200 indicando modo configuración y la GUI muestra el asistente

#### Scenario: Ruta normal en modo configuración
- **WHEN** se llama a `GET /lists` en modo configuración
- **THEN** la API responde 503 indicando qué falta por configurar

#### Scenario: Configurado sin Client Secret
- **WHEN** están el Client ID y la `API_KEY` pero no el Client Secret
- **THEN** el servicio no está en modo configuración

### Requirement: Asistente inicial
El asistente SHALL pedir el Client ID de Trakt y, como campo opcional, el Client Secret, con un enlace a la página de aplicaciones de Trakt y una explicación de que las aplicaciones nuevas no tienen Client Secret. SHALL generar una `API_KEY` aleatoria, que MUST mostrarse una sola vez, al terminar, con la opción de copiarla.

#### Scenario: Configuración completada
- **WHEN** el usuario completa el asistente con un código válido
- **THEN** la configuración se guarda, la `API_KEY` generada se muestra una vez y el servicio sale del modo configuración sin reiniciar

#### Scenario: Credencial de Trakt vacía
- **WHEN** el usuario deja vacío el Client ID
- **THEN** el asistente indica el campo que falta y no guarda nada

#### Scenario: Sin Client Secret
- **WHEN** el usuario completa el asistente solo con el Client ID
- **THEN** la configuración se guarda y el servicio sale del modo configuración
