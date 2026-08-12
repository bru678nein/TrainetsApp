import type { UseQueryResult } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Consulta } from "./estados";

/** Sólo los tres campos que `Consulta` mira. */
function consultaFalsa<T>(estado: Partial<UseQueryResult<T>>): UseQueryResult<T> {
  return { isPending: false, isError: false, data: undefined, ...estado } as UseQueryResult<T>;
}

function montarCon<T>(estado: Partial<UseQueryResult<T>>, vacio?: Parameters<typeof Consulta<T>>[0]["vacio"]) {
  return render(
    <Consulta consulta={consultaFalsa<T>(estado)} que="los datos" vacio={vacio}>
      {() => <p>contenido</p>}
    </Consulta>,
  );
}

describe("los tres estados", () => {
  it("cargando lo anuncia y no muestra contenido", () => {
    montarCon({ isPending: true });
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("contenido")).not.toBeInTheDocument();
  });

  it("el error lo anuncia y no se queda cargando", () => {
    montarCon({ isError: true });
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("con datos muestra el contenido y ningún estado", () => {
    montarCon({ data: [1, 2] });
    expect(screen.getByText("contenido")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("el estado vacío, que es el que importa", () => {
  it("dice el motivo y no un 'sin datos' genérico", () => {
    // Va por encima de los otros dos, y el motivo es que "no hay
    // datos" no contesta nada. Un panel sin series registradas espera al atleta;
    // un entrenador sin atletas se espera a sí mismo. Mismo vacío, dos pasos
    // siguientes distintos.
    montarCon({ data: [] }, { cuando: (d: number[]) => d.length === 0, motivo: "Nadie registró todavía." });
    expect(screen.getByText("Nadie registró todavía.")).toBeInTheDocument();
    expect(screen.queryByText("contenido")).not.toBeInTheDocument();
  });

  it("sin datos vacíos, el contenido se muestra igual", () => {
    // El control: una condición de vacío mal escrita esconde datos que sí están.
    montarCon({ data: [1] }, { cuando: (d: number[]) => d.length === 0, motivo: "Nada." });
    expect(screen.getByText("contenido")).toBeInTheDocument();
  });

  it("cargando gana sobre vacío: los datos todavía no llegaron", () => {
    // Sin este orden, la primera pintura de cada pantalla dice "no hay nada"
    // durante un instante y después aparecen los datos. Se lee como un error.
    montarCon({ isPending: true }, { cuando: () => true, motivo: "Nada." });
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByText("Nada.")).not.toBeInTheDocument();
  });
});
