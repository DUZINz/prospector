/*
 * Checagem minima da calculadora de orcamento (#orcamento).
 *
 * Rodar:  node test_calculadora.mjs
 *
 * Os dois arquivos sao scripts de navegador (sem export), entao sao avaliados
 * num contexto vm com um `document` de mentira — so o suficiente para o
 * addEventListener do fim de script.js nao explodir.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const NOMES = [
  "BASES_PROJETO", "MODULOS_EXTRAS",
  "calcularOrcamento", "montarBriefing", "montarOpcao",
];
// `const` no topo do script nao vira propriedade do global, entao os dois
// arquivos rodam juntos e a ultima expressao devolve o que interessa.
const fonte = ["data/precos.js", "js/script.js"]
  .map((a) => readFileSync(a, "utf8"))
  .concat(`({ ${NOMES.join(", ")} })`)
  .join("\n");

const { BASES_PROJETO, MODULOS_EXTRAS, calcularOrcamento, montarBriefing, montarOpcao } =
  vm.runInNewContext(fonte, { document: { addEventListener() {} } });

// A tabela e a fonte do preco: se um valor mudar sem querer, quebra aqui.
assert.equal(BASES_PROJETO.length, 8);
assert.equal(MODULOS_EXTRAS.length, 6);
assert.equal(BASES_PROJETO[0].preco, 620);
assert.equal(BASES_PROJETO.at(-1).preco, 5900);
// join() e nao deepEqual: objeto vindo do vm tem outro prototype e o
// deepStrictEqual reprova por isso mesmo com os valores iguais.
assert.equal(MODULOS_EXTRAS.map((m) => m.preco).join(), "1790,1190,2690,590,1390,1690");

// Sem extras: o orcamento e a base pura.
const base = BASES_PROJETO[0];
assert.equal(calcularOrcamento(base, []).total, 620);
assert.equal(calcularOrcamento(base, []).dias, 3);

// Com extras: preco e prazo somam.
const extras = [MODULOS_EXTRAS[0], MODULOS_EXTRAS[3]]; // 1790 + 590, 7 + 2 dias
assert.equal(calcularOrcamento(base, extras).total, 620 + 2380);
assert.equal(calcularOrcamento(base, extras).dias, 3 + 9);

// O briefing leva escopo, total e prazo — e nao inventa secao de extras vazia.
const texto = montarBriefing(base, extras);
assert.ok(texto.includes(base.nome));
extras.forEach((m) => assert.ok(texto.includes(m.nome), m.nome));
assert.ok(/Total estimado: R\$\s?3\.000/.test(texto), texto);
assert.ok(texto.includes("12 dias úteis"), texto);
assert.ok(!montarBriefing(base, []).includes("Módulos extras"));

// Base = radio com a primeira ja marcada; extra = checkbox, nenhum marcado.
assert.ok(montarOpcao(base, 0, "base").includes('type="radio"'));
assert.ok(montarOpcao(base, 0, "base").includes("checked"));
assert.ok(!montarOpcao(base, 1, "base").includes("checked"));
assert.ok(montarOpcao(MODULOS_EXTRAS[0], 0, "extra").includes('type="checkbox"'));
assert.ok(!montarOpcao(MODULOS_EXTRAS[0], 0, "extra").includes("checked"));

console.log("calculadora ok");
