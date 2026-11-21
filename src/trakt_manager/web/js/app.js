/**
 * Punto de entrada de la GUI.
 *
 * Decide a qué vista ir según el estado del servicio:
 *   - modo configuración           → asistente (#/configurar)
 *   - configurado y sin clave      → acceso (#/acceso)
 *   - configurado y con clave      → la sección pedida
 * y registra las secciones en el enrutador.
 */

import { getApiKey, onSessionProblem } from "./api.js";
import { notice, replaceChildren } from "./dom.js";
import { beforeNavigate, navigate, route, startRouter } from "./router.js";
import {
  isSetupMode,
  logout,
  markNotConfigured,
  refreshSetupState,
  refreshTraktBadge,
  showChrome,
} from "./session.js";
import { renderDefinitions } from "./views/definitions.js";
import { renderLists } from "./views/lists.js";
import { renderLogin } from "./views/login.js";
import { renderSettings } from "./views/settings.js";
import { renderSetup } from "./views/setup.js";
import { renderSync } from "./views/sync.js";
import { renderTrakt } from "./views/trakt.js";

route("configurar", renderSetup);
route("acceso", renderLogin);
route("definiciones", renderDefinitions);
route("sincronizar", renderSync);
route("listas", renderLists);
route("trakt", renderTrakt);
route("ajustes", renderSettings);

beforeNavigate(async (section) => {
  if (isSetupMode() === null) {
    try {
      await refreshSetupState();
    } catch (error) {
      replaceChildren(document.getElementById("view"), notice("error", error.message));
      return false;
    }
  }

  if (isSetupMode()) {
    showChrome(false);
    if (section !== "configurar") {
      navigate("/configurar");
      return false;
    }
    return true;
  }

  if (section === "configurar") {
    navigate(getApiKey() ? "/definiciones" : "/acceso");
    return false;
  }
  if (!getApiKey()) {
    showChrome(false);
    if (section !== "acceso") {
      navigate("/acceso");
      return false;
    }
    return true;
  }
  if (section === "acceso") {
    navigate("/definiciones");
    return false;
  }

  showChrome(true);
  refreshTraktBadge();
  return true;
});

onSessionProblem({
  // Clave incorrecta (por ejemplo, regenerada desde otro navegador): se vuelve al acceso.
  unauthorized: () => {
    logout();
    navigate("/acceso");
  },
  // El servicio ha perdido la configuración: se vuelve al asistente.
  notConfigured: () => {
    markNotConfigured();
    navigate("/configurar");
  },
});

document.getElementById("logout-button").addEventListener("click", () => {
  logout();
  navigate("/acceso");
});

startRouter();
