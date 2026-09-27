import { ensureBundle } from "../src/index.js";

const models: Record<string, string> = {
    base: "receptron/laya-onnx",
    fallacy: "BryanSnappCTO/laya-fallacies-onnx",
};

const requested = process.argv.slice(2);
const names = requested.length ? requested : Object.keys(models);
const unknown = names.filter((name) => !Object.hasOwn(models, name));

if (unknown.length) throw new Error(`unknown model ${unknown.join(", ")}; expected one of ${Object.keys(models).join(", ")}`);

for (const name of names) {
    const dir = await ensureBundle({
        repo: models[name],
        onProgress: ({ file, received, total }) => total && process.stderr.write(`\r${file}: ${((received / total) * 100).toFixed(0)}%   `),
    });
    process.stderr.write("\n");
    console.log(`${name}: ${dir}`);
}
