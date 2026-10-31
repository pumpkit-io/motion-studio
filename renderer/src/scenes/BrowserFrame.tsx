import { FONT_WEIGHT, TEXT_WEIGHT, type LoadedFont } from "../lib/fonts";

// Browser chrome stays a neutral light grey whatever the brand, like a real window.
const CHROME = { bar: "#EDEBE5", rule: "#DCD9D1", field: "#FFFFFF", text: "#5B5A55", body: "#F3F2EE" };
const LIGHTS = ["#FF5F57", "#FEBC2E", "#28C840"];

/** The title bar of a browser window: traffic lights and an address field. */
export const BrowserBar: React.FC<{ height: number; address: string | null; font: LoadedFont }> = ({
  height,
  address,
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
      <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>
        <div
          style={{
            fontFamily: font.family,
            fontSize: 17 * u,
            fontWeight: font.family === "Inter" ? TEXT_WEIGHT : FONT_WEIGHT,
            color: CHROME.text,
            backgroundColor: CHROME.field,
            borderRadius: 8 * u,
            minWidth: 420 * u,
            textAlign: "center",
            padding: `${5 * u}px ${24 * u}px`,
            boxSizing: "border-box",
            whiteSpace: "nowrap",
          }}
        >
          {/* A non-breaking space keeps an empty field its full height. */}
          {address ?? " "}
        </div>
      </div>
      <div style={{ width: 60 * u }} />
    </div>
  );
};

export const BROWSER_BODY = CHROME.body;
