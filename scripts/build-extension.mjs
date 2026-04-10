import esbuild from "esbuild";

const watch = process.argv.includes("--watch");

const common = {
  bundle: true,
  sourcemap: false,
  target: ["chrome114"],
  jsx: "automatic",
  logLevel: "info",
  ...(watch ? { watch: true } : {})
};

await esbuild.build({
  ...common,
  entryPoints: ["extension/popup/popup.jsx"],
  outfile: "extension/popup/popup.js",
  format: "iife"
});

await esbuild.build({
  ...common,
  entryPoints: ["extension/injected/meetingOverlay.jsx"],
  outfile: "extension/injected/meetingOverlay.js",
  format: "iife"
});

console.log("Extension build completed.");

if (watch) {
  console.log("Watching extension files for changes...");
}
