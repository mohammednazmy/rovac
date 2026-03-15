import { PanelExtensionContext } from "@foxglove/extension";
import { ReactElement, useCallback, useEffect, useLayoutEffect, useState } from "react";
import { createRoot } from "react-dom/client";

const TOPIC = "/phone/flashlight";
const SCHEMA = "std_msgs/msg/Bool";

function FlashlightPanel({ context }: { context: PanelExtensionContext }): ReactElement {
  const [isOn, setIsOn] = useState(false);
  const [renderDone, setRenderDone] = useState<(() => void) | undefined>();

  useLayoutEffect(() => {
    context.onRender = (_renderState, done) => {
      setRenderDone(() => done);
    };
    context.watch("topics");

    // Advertise that we publish to /phone/flashlight
    try {
      context.advertise?.(TOPIC, SCHEMA, { datatypes: new Map() });
    } catch (e) {
      console.warn("advertise failed, trying without options", e);
      try { context.advertise?.(TOPIC, SCHEMA); } catch (e2) { console.error("advertise failed", e2); }
    }
  }, [context]);

  useEffect(() => {
    renderDone?.();
  }, [renderDone]);

  const doPublish = useCallback((value: boolean) => {
    console.log(`[Flashlight] Publishing ${value} to ${TOPIC}`);
    try {
      context.publish?.(TOPIC, { data: value });
      console.log("[Flashlight] Published successfully");
    } catch (e) {
      console.error("[Flashlight] Publish error:", e);
    }
  }, [context]);

  const toggle = useCallback(() => {
    const newState = !isOn;
    setIsOn(newState);
    doPublish(newState);
  }, [isOn, doPublish]);

  const turnOn = useCallback(() => {
    setIsOn(true);
    doPublish(true);
  }, [doPublish]);

  const turnOff = useCallback(() => {
    setIsOn(false);
    doPublish(false);
  }, [doPublish]);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
        gap: "12px",
        fontFamily: "sans-serif",
        background: isOn ? "#1a1a0a" : "#1a1a2e",
        transition: "background 0.3s",
      }}
    >
      {/* Big toggle button */}
      <button
        onClick={toggle}
        style={{
          width: "120px",
          height: "120px",
          borderRadius: "50%",
          border: `4px solid ${isOn ? "#ffd700" : "#444"}`,
          background: isOn
            ? "radial-gradient(circle, #ffd700 0%, #ff8c00 60%, #8B4513 100%)"
            : "radial-gradient(circle, #333 0%, #1a1a1a 100%)",
          color: isOn ? "#000" : "#888",
          fontSize: "32px",
          cursor: "pointer",
          boxShadow: isOn
            ? "0 0 40px rgba(255, 215, 0, 0.6), 0 0 80px rgba(255, 140, 0, 0.3)"
            : "0 2px 8px rgba(0,0,0,0.5)",
          transition: "all 0.3s",
          outline: "none",
        }}
      >
        {isOn ? "\u2600" : "\u25CF"}
      </button>

      <div
        style={{
          color: isOn ? "#ffd700" : "#666",
          fontSize: "18px",
          fontWeight: "bold",
          transition: "color 0.3s",
        }}
      >
        {isOn ? "HEADLIGHT ON" : "HEADLIGHT OFF"}
      </div>

      {/* On/Off buttons */}
      <div style={{ display: "flex", gap: "8px" }}>
        <button
          onClick={turnOn}
          style={{
            padding: "8px 20px",
            background: isOn ? "#ffd700" : "#333",
            color: isOn ? "#000" : "#aaa",
            border: "1px solid #555",
            borderRadius: "4px",
            cursor: "pointer",
            fontSize: "14px",
          }}
        >
          ON
        </button>
        <button
          onClick={turnOff}
          style={{
            padding: "8px 20px",
            background: !isOn ? "#4ecca3" : "#333",
            color: !isOn ? "#000" : "#aaa",
            border: "1px solid #555",
            borderRadius: "4px",
            cursor: "pointer",
            fontSize: "14px",
          }}
        >
          OFF
        </button>
      </div>

      <div style={{ color: "#555", fontSize: "11px", marginTop: "4px" }}>
        {TOPIC}
      </div>
    </div>
  );
}

export function initFlashlightPanel(context: PanelExtensionContext): () => void {
  const root = createRoot(context.panelElement);
  root.render(<FlashlightPanel context={context} />);
  return () => { root.unmount(); };
}
