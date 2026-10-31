import { TEXT_WEIGHT, type LoadedFont } from "../lib/fonts";

// A dark terminal theme whatever the brand, after the Pumpkit launch video's Claude Code window.
const CHROME = { bar: "#2A2A3C", rule: "#34344A", text: "#A6A7C0", body: "#1D1D2D" };
const LIGHTS = ["#FF5F57", "#FEBC2E", "#28C840"];

/** The title bar of a terminal window: traffic lights and a centred title. */
export const TerminalBar: React.FC<{ height: number; title: string | null; font: LoadedFont }> = ({
  height,
  title,
  font,
}) => {
  const u = height / 44;
  return (
    <div
      style={{
        height,
        display: "flex",
        alignItems: "center",
        padding: `0 ${18 * u}px`,
        gap: 9 * u,
        backgroundColor: CHROME.bar,
        borderBottom: `${Math.max(1, u)}px solid ${CHROME.rule}`,
        boxSizing: "border-box",
      }}
    >
      {LIGHTS.map((c) => (
        <div key={c} style={{ width: 14 * u, height: 14 * u, borderRadius: 7 * u, backgroundColor: c }} />
      ))}
      <div
        style={{
          flex: 1,
          textAlign: "center",
          fontFamily: font.family,
          fontSize: 17 * u,
          fontWeight: TEXT_WEIGHT,
          color: CHROME.text,
          whiteSpace: "nowrap",
          overflow: "hidden",
        }}
      >
        {title ?? ""}
      </div>
      <div style={{ width: 60 * u }} />
    </div>
  );
};

export const TERMINAL_BODY = CHROME.body;
