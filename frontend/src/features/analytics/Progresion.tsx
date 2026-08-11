import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useProgresion } from "../../api/consultas";
import { Consulta } from "../../components/estados";
import { elMasSeguido } from "./ejercicios";

export function Progresion({ atletaId }: { atletaId: string }) {
  const consulta = useProgresion(atletaId);
  const [elegido, setElegido] = useState<string | null>(null);

  return (
    <section>
      <h3>Progresión de carga</h3>
      <Consulta
        consulta={consulta}
        que="la progresión"
        vacio={{
          cuando: (series) => series.length === 0,
          motivo: "Todavía no hay cargas registradas para este atleta.",
        }}
      >
        {(series) => {
          const actual = elegido ?? elMasSeguido(series);
          const serie = series.find((s) => s.exercise === actual);
          return (
            <>
              <label>
                Ejercicio{" "}
                <select value={actual ?? ""} onChange={(e) => setElegido(e.target.value)}>
                  {series.map((s) => (
                    <option key={s.exercise} value={s.exercise}>
                      {s.exercise}
                    </option>
                  ))}
                </select>
              </label>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={serie?.points ?? []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--borde)" vertical={false} />
                  <XAxis dataKey="week" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} unit=" kg" width={64} />
                  <Tooltip />
                  {/* `connectNulls` en false, y es lo único que importa de este
                      gráfico. En true, una semana prescrita sin registrar se
                      dibuja como si la línea pasara por ahí: el hueco desaparece
                      y la progresión se lee continua cuando no lo fue. */}
                  <Line
                    type="monotone"
                    dataKey="load_kg"
                    stroke="var(--hecho)"
                    connectNulls={false}
                    dot
                  />
                </LineChart>
              </ResponsiveContainer>
            </>
          );
        }}
      </Consulta>
    </section>
  );
}
