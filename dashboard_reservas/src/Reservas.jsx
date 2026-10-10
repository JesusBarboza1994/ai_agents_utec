import { useCallback, useEffect, useMemo, useState } from "react";

const ESTADOS = ["confirmada", "modificada", "pendiente_staff", "cancelada"];

export default function Reservas() {
  const [reservas, setReservas] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [filtro, setFiltro] = useState("todas");
  const [busqueda, setBusqueda] = useState("");

  const cargar = useCallback(async () => {
    setCargando(true);
    setError("");
    try {
      const res = await fetch("/api/reservas");
      if (!res.ok) throw new Error(`El servidor respondio ${res.status}`);
      setReservas(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const visibles = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    return reservas
      .filter((r) => filtro === "todas" || r.estado === filtro)
      .filter(
        (r) =>
          !q ||
          [r.id, r.nombre, r.telefono, r.zona, r.mesa_id]
            .join(" ")
            .toLowerCase()
            .includes(q)
      )
      .sort((a, b) => `${a.fecha} ${a.hora}`.localeCompare(`${b.fecha} ${b.hora}`));
  }, [reservas, filtro, busqueda]);

  return (
    <div className="contenedor">
      <header className="cabecera">
        <h1>Reservas</h1>
        <button onClick={cargar} disabled={cargando}>
          {cargando ? "Cargando..." : "Actualizar"}
        </button>
      </header>

      <div className="controles">
        <input
          type="search"
          placeholder="Buscar por nombre, telefono, id, zona..."
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
        />
        <select value={filtro} onChange={(e) => setFiltro(e.target.value)}>
          <option value="todas">Todos los estados</option>
          {ESTADOS.map((e) => (
            <option key={e} value={e}>
              {e}
            </option>
          ))}
        </select>
        <span className="contador">{visibles.length} de {reservas.length}</span>
      </div>

      {error && (
        <p className="error">
          No se pudieron cargar las reservas: {error}. Verifica que el servidor corra con
          CLEMENTE_DEBUG_ROUTES=1.
        </p>
      )}

      <div className="tabla-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Cliente</th>
              <th>Telefono</th>
              <th>Fecha</th>
              <th>Hora</th>
              <th>Personas</th>
              <th>Zona</th>
              <th>Mesa</th>
              <th>Estado</th>
              <th>Notas</th>
            </tr>
          </thead>
          <tbody>
            {visibles.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.nombre}</td>
                <td>{r.telefono}</td>
                <td>{r.fecha}</td>
                <td>{r.hora}</td>
                <td>{r.personas}</td>
                <td>{r.zona}</td>
                <td>{r.mesa_id}</td>
                <td>
                  <span className={`estado ${r.estado}`}>{r.estado}</span>
                </td>
                <td>{r.notas}</td>
              </tr>
            ))}
            {!cargando && !error && visibles.length === 0 && (
              <tr>
                <td colSpan={10} className="vacio">
                  No hay reservas.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
