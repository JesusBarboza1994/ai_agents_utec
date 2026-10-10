import { useState } from "react";
import Reservas from "./Reservas.jsx";
import Chats from "./Chats.jsx";

const VISTAS = [
  { id: "reservas", etiqueta: "Reservas", Componente: Reservas },
  { id: "chats", etiqueta: "Chats", Componente: Chats },
];

export default function App() {
  const [vista, setVista] = useState("reservas");
  const { Componente } = VISTAS.find((v) => v.id === vista);

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="marca">Clemente</div>
        <nav>
          {VISTAS.map((v) => (
            <button
              key={v.id}
              className={v.id === vista ? "nav activo" : "nav"}
              onClick={() => setVista(v.id)}
            >
              {v.etiqueta}
            </button>
          ))}
        </nav>
      </aside>
      <main className="contenido">
        <Componente />
      </main>
    </div>
  );
}
