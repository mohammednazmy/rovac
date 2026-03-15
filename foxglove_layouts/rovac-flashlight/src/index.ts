import { ExtensionContext } from "@foxglove/extension";
import { initFlashlightPanel } from "./FlashlightPanel";

export function activate(extensionContext: ExtensionContext): void {
  extensionContext.registerPanel({
    name: "rovac-flashlight",
    initPanel: initFlashlightPanel,
  });
}
