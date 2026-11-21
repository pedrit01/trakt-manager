# Spec Delta

## MODIFIED Requirements

### Requirement: Credenciales de aplicación por configuración
El sistema SHALL leer el Client ID y, si existe, el Client Secret de la aplicación de Trakt desde la configuración (`TRAKT_CLIENT_ID` y `TRAKT_CLIENT_SECRET`). El Client Secret MUST ser opcional: sin él, la autorización, la renovación y la revocación se hacen solo con el Client ID. Si existe, MUST enviarse a Trakt en esas operaciones.

#### Scenario: Falta el Client ID
- **WHEN** se lanza cualquier operación que llame a Trakt sin `TRAKT_CLIENT_ID` configurado
- **THEN** la operación falla antes de contactar con Trakt con un error que nombra la variable que falta

#### Scenario: Operación de solo lectura sin secreto
- **WHEN** se ejecuta una previsualización (dry-run) con `TRAKT_CLIENT_ID` pero sin `TRAKT_CLIENT_SECRET`
- **THEN** la operación se completa sin pedir autenticación

#### Scenario: Autorización sin secreto
- **WHEN** se inicia sesión con una aplicación de Trakt que no tiene Client Secret
- **THEN** el device flow se completa sin enviar `client_secret` a Trakt

#### Scenario: Aplicación con secreto
- **WHEN** `TRAKT_CLIENT_SECRET` está configurado
- **THEN** se envía a Trakt al sondear el device flow, al renovar y al revocar el token

#### Scenario: Trakt exige el secreto
- **WHEN** Trakt rechaza como cliente no válido una autorización o renovación hecha sin secreto
- **THEN** el error indica que esa aplicación de Trakt parece necesitar un Client Secret
