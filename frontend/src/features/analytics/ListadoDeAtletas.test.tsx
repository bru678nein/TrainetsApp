import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { montar } from "../../lib/pruebas";
import { ListadoDeAtletas } from "./ListadoDeAtletas";

const pedir = vi.hoisted(() => vi.fn());
vi.mock("../../api/useApi", () => ({ useApi: () => pedir }));

const ATLETAS = [
  { id: "a1", full_name: "Primero", level: "intermedio" },
  { id: "a2", full_name: "Segundo", level: null },
  { id: "a3", full_name: "Tercero", level: null },
];

describe("el listado de atletas", () => {
  beforeEach(() => {
    pedir.mockReset();
  });

  it("muestra los que devuelve el API", async () => {
    pedir.mockResolvedValue(ATLETAS);
    montar(<ListadoDeAtletas />);
    expect(await screen.findByText("Primero")).toBeInTheDocument();
  });

  it("no filtra del lado del navegador", async () => {
    // La regla de qué atletas ve un entrenador vive en la base: RLS decide de
    // quién son, y el endpoint decide qué estados cuentan como vigentes.
    // Repetir cualquiera de las dos acá crea una segunda copia que se
    // desincroniza — y la que se desincroniza siempre es la que nadie recuerda
    // haber escrito. Si aparece un filtro en el cliente, este test lo caza.
    pedir.mockResolvedValue(ATLETAS);
    montar(<ListadoDeAtletas />);
    await screen.findByText("Primero");
    expect(screen.getAllByRole("listitem")).toHaveLength(ATLETAS.length);
  });

  it("cada uno lleva a su panel", async () => {
    pedir.mockResolvedValue(ATLETAS);
    montar(<ListadoDeAtletas />);
    const enlace = await screen.findByRole("link", { name: "Segundo" });
    expect(enlace).toHaveAttribute("href", "/atletas/a2");
  });

  it("mientras carga lo dice", () => {
    pedir.mockReturnValue(new Promise(() => {}));
    montar(<ListadoDeAtletas />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("si falla lo dice, y no se queda cargando para siempre", async () => {
    pedir.mockRejectedValue(new Error("403"));
    montar(<ListadoDeAtletas />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("sin atletas explica que no hay, en vez de mostrar una lista vacía", async () => {
    pedir.mockResolvedValue([]);
    montar(<ListadoDeAtletas />);
    expect(await screen.findByText("Todavía no cargaste ningún atleta.")).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });
});
