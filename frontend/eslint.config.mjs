import eslint from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import typescriptEslint from "typescript-eslint";

const eslintConfig = typescriptEslint.config(
	{ ignores: [".next/**", "node_modules/**", "next-env.d.ts"] },
	eslint.configs.recommended,
	...typescriptEslint.configs.recommended,
	{
		files: ["**/*.{js,mjs,cjs,ts,tsx}"],
		languageOptions: { globals: { ...globals.browser, ...globals.node } },
	},
	{
		files: ["src/**/*.{ts,tsx}"],
		plugins: { "react-hooks": reactHooks },
		rules: reactHooks.configs.flat.recommended.rules,
	},
);

export default eslintConfig;