import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorDelApi } from "../../api/cliente";
import { useAceptarInvitacion } from "../../api/consultas";
import { Cargando } from "../../components/estados";
import { olvidar, recuperar } from "./tokenEnTransito";

/**
 * Cada rechazo con su salida, que es la razón por la que el backend los
 * distingue en vez de contestar un `400` para todo.
 *
 * Un link vencido y uno inventado se ven igual desde acá y no lo son: del
 * primero se sale pidiendo otro, del segundo revisando lo que se pegó. Y
 * `vinculo_archivado` es el único donde la persona no puede hacer nada sola.
 */
const MENSAJES: Record<string, string> = {
  invitacion_inexistente: "Este link no existe. Revisá que lo hayas copiado entero.",
  invitacion_vencida: "Este link venció. Pedile a tu entrenador que te mande uno nuevo.",
  invitacion_usada: "Este link ya se usó. Si no fuiste vos, avisale a tu entrenador.",
  ya_sos_atleta_de_ese_entrenador: "Ya sos atleta de ese entrenador.",
  vinculo_archivado: "Tu entrenador cerró este vínculo. Sólo él puede volver a abrirlo.",
};

function mensajeDe(error: unknown): string {
  const conocido = error instanceof ErrorDelApi && error.detalle ? MENSAJES[error.detalle] : null;
  // El genérico cubre lo que no es un rechazo del ciclo: un 401, un 500, la red
  // caída. Decir "el link venció" ahí sería mandar a pedir otro que tampoco va
  // a andar.
  return conocido ?? "No se pudo aceptar la invitación.";
}

/**
 * La pantalla que consume el link, y el único lugar de la aplicación al que se
 * llega sin ser todavía atleta de nadie.
 *
 * Se monta ya adentro del portón de sesión, así que cuando corre hay identidad
 * — y por eso mismo no puede ser quien guarde el token: cuando el proveedor
 * mostró su formulario, esta pantalla no existía. De guardarlo se encarga el
 * punto de entrada. Acá sólo se lo lee, de la dirección si todavía está, y de lo
 * guardado si no.
 */
export function Aceptar() {
  const { token: enLaUrl } = useParams();
  const aceptar = useAceptarInvitacion();
  // La dirección manda cuando todavía lo trae; lo guardado es el respaldo para
  // cuando el proveedor devolvió el navegador a otro lado. Guardar acá sería un
  // efecto durante el render, y además volvería a escribir lo que `olvidar`
  // acaba de borrar. Quien guarda es el punto de entrada, antes del portón.
  const [token] = useState(() => enLaUrl ?? recuperar());

  // React monta dos veces en desarrollo, y esto gasta un link de un solo uso.
  const yaSeMando = useRef(false);
  const { mutate } = aceptar;
  useEffect(() => {
    if (!token || yaSeMando.current) return;
    yaSeMando.current = true;
    mutate(token, { onSettled: olvidar });
  }, [token, mutate]);

  if (!token) {
    return (
      <section>
        <h2>Falta el link</h2>
        <p>Abrí el link que te mandó tu entrenador, entero y tal como te llegó.</p>
        <Link to="/">Ir al inicio</Link>
      </section>
    );
  }

  if (aceptar.isPending || aceptar.isIdle) return <Cargando que="tu invitación" />;

  if (aceptar.isError) {
    return (
      <section>
        <h2>No pudimos asociarte</h2>
        <p className="estado estado--falla" role="alert">
          {mensajeDe(aceptar.error)}
        </p>
        <Link to="/">Ir al inicio</Link>
      </section>
    );
  }

  return (
    <section>
      <h2>Listo, ya estás asociado</h2>
      <p>Tu entrenador ya puede ver tu entrenamiento y vos el programa que te armó.</p>
      <Link to="/">Ir al inicio</Link>
    </section>
  );
}
