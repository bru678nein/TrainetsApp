import "@testing-library/jest-dom/vitest";

/**
 * jsdom no implementa `<dialog>`: `showModal` y `close` no existen.
 *
 * Este sustituto abre y cierra, y nada más. Conviene ser explícito sobre lo que
 * **no** cubre, porque es justamente lo que motivó usar `<dialog>` nativo: el
 * foco atrapado adentro, el fondo inerte, el cierre con Escape y la devolución
 * del foco al abridor los pone el navegador, y acá no corren. Los tests
 * verifican lo nuestro —qué botón hace qué, qué dice el diálogo, qué pedido
 * sale—, no la semántica que delegamos.
 *
 * Por eso el caso del foco inicial afirma sobre el atributo `autofocus` y no
 * sobre dónde quedó el foco: dónde queda lo decide `showModal`, que acá es esto.
 */
const dialogo = window.HTMLDialogElement?.prototype;
if (dialogo && !dialogo.showModal) {
  dialogo.showModal = function () {
    this.open = true;
  };
  dialogo.close = function (valor?: string) {
    this.open = false;
    if (valor !== undefined) this.returnValue = valor;
    this.dispatchEvent(new Event("close"));
  };
}
