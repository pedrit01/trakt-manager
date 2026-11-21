/**
 * Vista de sincronización de una definición (#/sincronizar/<nombre>).
 *
 * Flujo: previsualizar (dry-run) → revisar el informe → sincronizar, que vuelve
 * a calcular los cambios y pide confirmación mostrándolos antes de tocar Trakt.
 */

import { ApiError, api } from "../api.js";
import { confirmDialog, h, notice, replaceChildren, toast } from "../dom.js";
import { navigate } from "../router.js";
import { refreshTraktBadge } from "../session.js";

/**
 * Pinta la vista de una definición.
 *
 * @param {HTMLElement} view
 * @param {string|null} name Nombre de la definición.
 */
export async function renderSync(view, name) {
  if (!name) {
    navigate("/definiciones");
    return;
  }
  const extras = h("input", { type: "checkbox", id: "include-extras" });
  const previewButton = h("button", { type: "button", className: "button", onClick: preview }, "Previsualizar");
  const syncButton = h("button", { type: "button", className: "button primary", onClick: synchronize }, "Sincronizar con Trakt");
  const output = h("div");

  replaceChildren(
    view,
    h("p", {}, h("a", { href: "#/definiciones" }, "← Definiciones")),
    h("h1", {}, `Sincronizar «${name}»`),
    h(
      "section",
      { className: "card" },
      h("label", { className: "checkbox" }, extras, "Incluir las entradas marcadas como extra"),
      h("p", { className: "hint" }, "Previsualizar no modifica tu cuenta. Sincronizar crea la lista si no existe o la actualiza para que coincida con la definición."),
      h("div", { className: "row" }, previewButton, syncButton),
    ),
    output,
  );

  /**
   * Llama a la sincronización (real o de prueba) y devuelve el resultado.
   *
   * @param {boolean} dryRun
   */
  function callSync(dryRun) {
    return api("POST", `/definitions/${encodeURIComponent(name)}/sync`, {
      query: { dry_run: String(dryRun), include_extras: String(extras.checked) },
    });
  }

  /** Deshabilita los botones mientras dura una operación. */
  function busy(isBusy, text) {
    previewButton.disabled = isBusy;
    syncButton.disabled = isBusy;
    if (isBusy) replaceChildren(output, h("p", { className: "muted" }, text));
  }

  /** Previsualiza sin modificar la cuenta. */
  async function preview() {
    busy(true, "Buscando las entradas en Trakt…");
    try {
      replaceChildren(output, renderResult(await callSync(true)));
    } catch (error) {
      replaceChildren(output, describeSyncError(error, preview));
    } finally {
      busy(false);
    }
  }

  /** Calcula los cambios, pide confirmación mostrándolos y sincroniza. */
  async function synchronize() {
    busy(true, "Calculando los cambios…");
    let planned;
    try {
      planned = await callSync(true);
    } catch (error) {
      replaceChildren(output, describeSyncError(error, synchronize));
      busy(false);
      return;
    }
    replaceChildren(output, renderResult(planned));
    busy(false);

    if (!planned.plan.compared_with_account) {
      replaceChildren(output, needsTraktSession());
      return;
    }
    if (!planChanges(planned.plan)) {
      toast("La lista ya coincide con la definición: no hay nada que cambiar.");
      return;
    }
    const confirmed = await confirmDialog({
      title: "¿Aplicar estos cambios en Trakt?",
      body: [h("p", {}, `Lista «${planned.list_name}»:`), changeSummary(planned.plan)],
      confirmLabel: "Sincronizar",
    });
    if (!confirmed) return;

    busy(true, "Sincronizando con Trakt…");
    try {
      const result = await callSync(false);
      replaceChildren(output, notice("ok", `Lista sincronizada (${result.plan.final_order.length} elementos).`), renderResult(result));
      refreshTraktBadge();
    } catch (error) {
      replaceChildren(output, describeSyncError(error, synchronize));
    } finally {
      busy(false);
    }
  }
}

/**
 * Bloque que explica que hace falta conectar con Trakt y ofrece hacerlo.
 *
 * @returns {HTMLElement}
 */
function needsTraktSession() {
  return notice(
    "warn",
    "Para sincronizar primero tienes que conectar con Trakt. ",
    h("a", { href: "#/trakt" }, "Conectar ahora"),
  );
}

/**
 * Traduce un error de sincronización a un bloque con, si tiene sentido, la opción de reintentar.
 *
 * @param {unknown} error
 * @param {Function} retry Acción a repetir.
 * @returns {HTMLElement}
 */
function describeSyncError(error, retry) {
  if (!(error instanceof ApiError)) return notice("error", String(error));
  if (error.status === 409 && /auth login|sesión/i.test(error.message)) return needsTraktSession();
  if (error.status === 409) return notice("warn", error.message); // p. ej. otra sincronización en curso: no se reintenta solo
  const canRetry = error.status === 502 || error.status === 0;
  return notice(
    "error",
    error.message,
    canRetry ? h("div", { className: "row" }, h("button", { type: "button", className: "button small", onClick: retry }, "Reintentar")) : null,
  );
}

/**
 * @param {object} plan SyncPlan de la API.
 * @returns {boolean} Si aplicar el plan cambiaría algo.
 */
function planChanges(plan) {
  return Boolean(plan.create_list || plan.metadata_changes.length || plan.to_add.length || plan.to_remove.length || plan.note_updates.length || plan.reorder);
}

/**
 * Resumen de los cambios de un plan, en texto.
 *
 * @param {object} plan
 * @returns {HTMLElement}
 */
function changeSummary(plan) {
  const lines = [];
  if (plan.create_list) lines.push("Crear la lista");
  for (const change of plan.metadata_changes) lines.push(`Cambiar ${change.field}: ${JSON.stringify(change.current)} → ${JSON.stringify(change.desired)}`);
  if (plan.to_add.length) lines.push(`Añadir ${plan.to_add.length} elementos`);
  if (plan.to_remove.length) lines.push(`Quitar ${plan.to_remove.length} elementos: ${plan.to_remove.map((item) => item.label).join(", ")}`);
  if (plan.note_updates.length) lines.push(`Actualizar ${plan.note_updates.length} notas`);
  if (plan.reorder) lines.push("Reordenar la lista");
  return h("ul", {}, lines.map((line) => h("li", {}, line)));
}

/**
 * Pinta el resultado de una sincronización o previsualización: resumen, cambios,
 * informe de resolución y avisos.
 *
 * @param {object} result SyncResult de la API.
 * @returns {HTMLElement}
 */
function renderResult(result) {
  const { plan, report } = result;
  const found = report.resolved.length;
  const missing = report.unresolved.length;

  return h(
    "section",
    { className: "card" },
    h("h2", {}, result.dry_run ? "Previsualización (no se ha modificado nada)" : "Resultado"),
    plan.compared_with_account ? null : notice("info", "Sin sesión de Trakt: se compara como si la lista no existiera."),
    h(
      "div",
      { className: "summary-grid" },
      stat("Encontradas", found),
      stat("No encontradas", missing),
      stat("A añadir", plan.to_add.length),
      stat("A quitar", plan.to_remove.length),
    ),
    planChanges(plan) ? changeSummary(plan) : notice("ok", "La lista ya coincide con la definición."),
    result.warnings.length ? notice("warn", h("strong", {}, "Avisos"), h("ul", {}, result.warnings.map((warning) => h("li", {}, warning)))) : null,
    plan.duplicates_skipped.length ? notice("info", `Repetidos en la definición (se añaden una vez): ${plan.duplicates_skipped.join(", ")}`) : null,
    h("h3", {}, "Qué se ha encontrado en Trakt"),
    h(
      "div",
      { className: "table-wrap" },
      h(
        "table",
        { className: "responsive" },
        h("thead", {}, h("tr", {}, h("th", {}, "#"), h("th", {}, "Entrada"), h("th", {}, "Encontrado en Trakt"), h("th", {}, "Elementos"))),
        h("tbody", {}, resolutionRows(report)),
      ),
    ),
  );
}

/**
 * Filas del informe de resolución, encontradas y no encontradas juntas en el
 * orden de la definición.
 *
 * @param {object} report ResolutionReport de la API.
 * @returns {HTMLElement[]}
 */
function resolutionRows(report) {
  const rows = [
    ...report.resolved.map((entry) => ({
      position: entry.position,
      cells: [
        entry.entry_title,
        [`${entry.matched_title}${entry.matched_year ? ` (${entry.matched_year})` : ""}`, h("div", { className: "muted small-text mono" }, `trakt:${entry.trakt_id}`)],
        String(entry.items.length),
      ],
    })),
    ...report.unresolved.map((item) => ({
      position: item.position,
      cells: [item.label, h("span", { className: "badge error" }, item.reason), "0"],
    })),
  ];
  // Una misma posición puede tener una fila encontrada y otra de episodios no encontrados:
  // el orden estable de sort las mantiene en ese orden.
  rows.sort((first, second) => first.position - second.position);
  return rows.map(({ position, cells: [entry, match, count] }) =>
    h(
      "tr",
      {},
      h("td", { "data-label": "#" }, String(position)),
      h("td", { "data-label": "Entrada" }, entry),
      h("td", { "data-label": "En Trakt" }, match),
      h("td", { "data-label": "Elementos", className: "number" }, count),
    ),
  );
}

/**
 * Celda de resumen con una cifra.
 *
 * @param {string} label
 * @param {number} value
 * @returns {HTMLElement}
 */
function stat(label, value) {
  return h("div", {}, h("strong", {}, String(value)), h("span", { className: "muted small-text" }, label));
}
