import { useGenerarInvitacion } from "../../api/consultas";
import { ErrorDelApi } from "../../api/cliente";

/** El link que se manda, armado con el origen desde el que se está mirando. */
function linkDe(token: string): string {
  return `${window.location.origin}/invitacion/${token}`;
}

function cuandoVence(iso: string): string {
  return new Date(iso).toLocaleDateString("es-AR", {
    day: "numeric",
    month: "long",
  });
}

function mensajeDe(error: unknown): string {
  if (error instanceof ErrorDelApi && error.detalle === "vinculo_archivado") {
    return "El vínculo está archivado. Reactivalo antes de invitar.";
  }
  return "No se pudo generar el link.";
}

/**
 * El link con el que un atleta reclama la ficha que el entrenador ya armó.
 *
 * El token se muestra **una sola vez**, y eso no es una decisión de esta
 * pantalla: la base guarda su hash y ninguna ruta lo puede volver a mostrar. Por
 * eso el texto lo dice antes de que la persona cierre la pestaña, y por eso el
 * botón deja de ofrecer "generar" y pasa a ofrecer "generar otro" — que además
 * invalida éste.
 */
export function Invitar({ atletaId }: { atletaId: string }) {
  const invitacion = useGenerarInvitacion();

  return (
    <section className="tarjeta">
      <h3>Invitación</h3>

      {invitacion.isSuccess ? (
        <>
          <p>
            Mandale este link. <strong>No se vuelve a mostrar</strong>, vence el{" "}
            {cuandoVence(invitacion.data.expires_at)} y sirve una sola vez.
          </p>
          <p>
            <input
              readOnly
              className="link-de-invitacion"
              value={linkDe(invitacion.data.token)}
              aria-label="Link de invitación"
              onFocus={(evento) => evento.currentTarget.select()}
            />
          </p>
        </>
      ) : null}

      <button
        type="button"
        className={invitacion.isSuccess ? undefined : "principal"}
        onClick={() => invitacion.mutate(atletaId)}
        disabled={invitacion.isPending}
      >
        {invitacion.isPending
          ? "Generando…"
          : invitacion.isSuccess
            ? "Generar otro (invalida el anterior)"
            : "Generar link de invitación"}
      </button>

      {invitacion.isError ? (
        <p className="estado estado--falla" role="alert">
          {mensajeDe(invitacion.error)}
        </p>
      ) : null}
    </section>
  );
}
