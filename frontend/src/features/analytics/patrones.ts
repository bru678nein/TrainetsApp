import { usePatrones } from "../../api/consultas";

/**
 * El nombre que un patrón de movimiento tiene, según el catálogo.
 *
 * La versión anterior lo fabricaba reemplazando guiones bajos, y eso es una
 * segunda fuente para un dato que la base ya declara: `bisagra_de_cadera_isquios`
 * salía como "bisagra de cadera isquios" cuando su nombre es "Bisagra de cadera
 * / isquios", y `pliometria` como "pliometria" cuando en la tabla dice
 * "PLIOMETRIA". Ninguna regla de texto recupera esas dos.
 *
 * El catálogo son once filas que no cambian nunca, así que se pide una vez y se
 * cachea para siempre; el costo de mirarlo es cero después de la primera vez.
 *
 * Cuando falta —todavía cargando, o un patrón que el catálogo no trae— se
 * devuelve el código tal cual. Es feo y es honesto: inventar una versión
 * "linda" es exactamente lo que este archivo viene a sacar.
 */
export function useNombreDePatron(): (codigo: string) => string {
  const { data } = usePatrones();
  return (codigo) => data?.find((p) => p.code === codigo)?.label_es ?? codigo;
}
