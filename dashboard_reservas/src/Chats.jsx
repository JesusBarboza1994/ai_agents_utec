import { useCallback, useEffect, useState } from "react";

const hora = (iso) =>
  new Date(iso).toLocaleString("es-PE", { dateStyle: "short", timeStyle: "short" });

const titulo = (c) => c.nombre || c.telefono || c.chat_key;

const iniciales = (c) => {
  const partes = (c.nombre || "").split(" ").filter(Boolean);
  if (partes.length) return (partes[0][0] + (partes[1]?.[0] || "")).toUpperCase();
  return "#";
};

// Color estable por chat, para distinguirlos de un vistazo.
const colorDe = (clave) => {
  let h = 0;
  for (const ch of clave) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return `hsl(${h} 45% 45%)`;
};

// Hoy: la hora; antes: la fecha.
const fechaCorta = (iso) => {
  const d = new Date(iso);
  return d.toDateString() === new Date().toDateString()
    ? d.toLocaleTimeString("es-PE", { timeStyle: "short" })
    : d.toLocaleDateString("es-PE", { day: "2-digit", month: "2-digit" });
};

export default function Chats() {
  const [chats, setChats] = useState([]);
  const [seleccionado, setSeleccionado] = useState(null);
  const [mensajes, setMensajes] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [busqueda, setBusqueda] = useState("");

  const pedir = async (url) => {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`El servidor respondio ${res.status}`);
    return res.json();
  };

  const cargarChats = useCallback(async () => {
    setCargando(true);
    setError("");
    try {
      const todos = await pedir("/api/chats");
      setChats(todos.filter((c) => c.canal === "whatsapp"));
    } catch (e) {
      setError(e.message);
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    cargarChats();
  }, [cargarChats]);

  useEffect(() => {
    if (!seleccionado) return;
    setMensajes([]);
    pedir(`/api/chats/${seleccionado.id}/mensajes`)
      .then(setMensajes)
      .catch((e) => setError(e.message));
  }, [seleccionado]);

  const visibles = chats.filter((c) =>
    [c.nombre, c.telefono, c.chat_key, c.ultimo_mensaje]
      .join(" ")
      .toLowerCase()
      .includes(busqueda.trim().toLowerCase())
  );

  return (
    <div className="chats">
      <section className="chats-lista">
        <header className="cabecera">
          <h1>Chats de WhatsApp</h1>
          <button onClick={cargarChats} disabled={cargando}>
            {cargando ? "..." : "Actualizar"}
          </button>
        </header>
        {error && <p className="error">{error}</p>}
        <input
          className="chats-busqueda"
          type="search"
          placeholder="Buscar chat..."
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
        />
        <div className="chat-items">
          {visibles.map((c) => (
            <button
              key={c.id}
              className={seleccionado?.id === c.id ? "chat-item activo" : "chat-item"}
              onClick={() => setSeleccionado(c)}
            >
              <span className="avatar" style={{ background: colorDe(c.chat_key) }}>
                {iniciales(c)}
              </span>
              <span className="chat-texto">
                <span className="chat-fila">
                  <strong className="chat-nombre">{titulo(c)}</strong>
                  <span className="fecha">{fechaCorta(c.ultimo_mensaje_en)}</span>
                </span>
                <span className="preview">{c.ultimo_mensaje}</span>
              </span>
            </button>
          ))}
        </div>
        {!cargando && !error && chats.length === 0 && <p className="vacio">No hay chats de WhatsApp.</p>}
      </section>

      <section className="conversacion">
        {!seleccionado ? (
          <p className="vacio">Selecciona un chat para ver sus mensajes.</p>
        ) : (
          <>
            <h2>{titulo(seleccionado)}</h2>
            <div className="mensajes">
              {mensajes.map((m) => (
                <div key={m.id} className={`burbuja ${m.rol === "user" ? "usuario" : "agente"}`}>
                  <span className="quien">{m.rol === "user" ? "Usuario" : "Agente"}</span>
                  {m.tipo === "image_url" ? (
                    <a href={m.contenido} target="_blank" rel="noreferrer">
                      <img src={m.contenido} alt="imagen enviada" />
                    </a>
                  ) : m.tipo === "audio_url" ? (
                    <>
                      <audio controls preload="none" src={m.contenido} />
                      {m.transcripcion && <p className="transcripcion">{m.transcripcion}</p>}
                    </>
                  ) : (
                    <p>{m.contenido}</p>
                  )}
                  <span className="fecha">{hora(m.creado)}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
