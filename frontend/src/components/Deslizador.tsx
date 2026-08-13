import { useId } from "react";

/**
 * Un rango con su valor a la vista, para elegir entre pocos números.
 *
 * Reemplaza al `input type=number` con flechitas, y el motivo no es estético:
 * con siete días o cuatro semanas, un campo numérico obliga a **apuntar a una
 * flecha de doce píxeles y contar clics**, o a seleccionar el texto y escribir
 * encima. Para un rango chico y conocido, arrastrar es un gesto y no una cuenta.
 *
 * Tres cosas que un `input type=range` pelado no da y hay que agregarle:
 *
 * - **El valor.** Un rango sin número es una posición sin dato. Va al lado, en
 *   cifras tabulares para que no salte de ancho al cambiar.
 * - **Los extremos.** Sin ellos no se sabe si el tope son cuatro semanas o
 *   dieciséis, que es justo lo que hay que saber para elegir.
 * - **El teclado**, que sí viene gratis: flechas, Inicio y Fin ya funcionan. Por
 *   eso esto no necesita el par de botones que sí necesita reordenar.
 */
export function Deslizador({
  etiqueta,
  valor,
  onCambio,
  min = 1,
  max,
  sufijo,
}: {
  etiqueta: string;
  valor: number;
  onCambio: (valor: number) => void;
  min?: number;
  max: number;
  sufijo?: string;
}) {
  const id = useId();

  // Con un solo valor posible el control no decide nada: un mesociclo de una
  // semana no tiene "qué semana". Se muestra el dato y no un rango que no se
  // puede mover, que sería un control muerto pidiendo que lo intenten.
  if (max <= min) {
    return (
      <p className="deslizador deslizador--fijo">
        <span className="deslizador__etiqueta">{etiqueta}</span>
        <strong className="deslizador__valor">{min}</strong>
        {sufijo ? <small>{sufijo}</small> : null}
      </p>
    );
  }

  return (
    <div className="deslizador">
      <label className="deslizador__etiqueta" htmlFor={id}>
        {etiqueta}
      </label>
      <span className="deslizador__extremo">{min}</span>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={1}
        value={valor}
        onChange={(e) => onCambio(Number(e.target.value))}
      />
      <span className="deslizador__extremo">{max}</span>
      <output htmlFor={id} className="deslizador__valor">
        {valor}
        {sufijo ? <small> {sufijo}</small> : null}
      </output>
    </div>
  );
}
