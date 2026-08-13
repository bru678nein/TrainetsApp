import { useRol } from "../lib/Rol";
import { ListadoDeAtletas } from "./atletas/ListadoDeAtletas";
import { MisSesiones } from "./entrenar/Entrenar";

/**
 * La pantalla de entrada, que no es la misma para los dos roles.
 *
 * Antes la raíz renderizaba siempre el listado del entrenador. Alguien mirando
 * como atleta veía su propia ficha dentro de una pantalla que ofrecía "agregar
 * atleta", "pausar" y "archivar" — acciones que la base le rechaza, pero
 * ofrecidas igual. Un botón que no puede funcionar es peor que un botón que no
 * está: promete algo y falla recién cuando alguien confía.
 *
 * El rol no cambia sólo la cabecera del pedido, cambia de qué se trata la
 * aplicación. Como entrenador es "mis atletas"; como atleta, "lo que tengo que
 * entrenar".
 */
export function Inicio() {
  const { rol } = useRol();
  return rol === "athlete" ? <MisSesiones /> : <ListadoDeAtletas />;
}
