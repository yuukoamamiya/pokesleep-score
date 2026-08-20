const fs = require('fs');
const path = require('path');
const Module = require('module');
const D = path.join(__dirname, 'data');

function evalJs(p, src) {
  const m = new Module(p);
  m._compile(src, p);
  return m.exports;
}

function load(name, exportNames) {
  const p = path.join(D, `pc_${name}.js`);
  let src = fs.readFileSync(p, 'utf8');
  src = src.replace(/^\s*import[^;]+;/gm, '');
  src = src.replace(/export\s+/g, '');
  // strip trailing `{ a, b }` leftover from export { ... }
  src = src.replace(/\{\s*pokedex\s*,\s*updatePoke\s*\}\s*$/, '');
  if (exportNames) {
    src += `\nmodule.exports = { ${exportNames.join(', ')} };`;
  }
  return evalJs(p, src);
}

function loadGame() {
  const p = path.join(D, 'pc_game.js');
  let src = fs.readFileSync(p, 'utf8');
  src = src.split('\n').filter(l => !/^\s*import /.test(l)).join('\n');
  src = src.replace(/export\s+/g, '');
  const start = src.indexOf('const gameMap = [');
  const end = src.indexOf(']', start) + 1;
  src = src.slice(0, start) + 'const gameMap = []' + src.slice(end);
  src += '\nmodule.exports = { POKEMON_MAX_LEVEL, EX_HELP_SPEED, FMB_MAP_INDEXES, areaBonusMax, mapSplitVer, SHINY_LOCK_POKEMONS, SP_POKEMONS };';
  return evalJs(p, src);
}

const out = {};
out.pokedex = load('pokedex', ['pokedex']).pokedex;
out.berryEnergy = load('berryEnergy', ['BERRY_ENERGY']).BERRY_ENERGY;
out.foodEnergy = load('valKey', ['FOOD_ENERGY']).FOOD_ENERGY;
out.skillEffects = load('skillEffects', ['skillEffects']).skillEffects;
out.nature = load('pokeNature', ['NATURE']).NATURE;
out.helpSpeed = load('helpSpeed', ['characterOptions', 'skillOptionsHelpSpeed', 'skillOptionsFoodPer', 'skillOptionsSkillPer', 'skillOptionsSkillLevel', 'skillOptionsMaxcarry', 'skillOptionsExtra', 'allHelpType', 'maxSkillCount']);
out.subSkills = load('pokeSkill', ['SUB_SKILLS']).SUB_SKILLS;
const game = loadGame();
out.game = {
  POKEMON_MAX_LEVEL: game.POKEMON_MAX_LEVEL,
  EX_HELP_SPEED: game.EX_HELP_SPEED,
  FMB_MAP_INDEXES: game.FMB_MAP_INDEXES,
  SHINY_LOCK_POKEMONS: game.SHINY_LOCK_POKEMONS,
  SP_POKEMONS: game.SP_POKEMONS,
  areaBonusMax: game.areaBonusMax,
};

for (const [k, v] of Object.entries(out)) {
  const p = path.join(D, `${k}.json`);
  fs.writeFileSync(p, JSON.stringify(v, null, 1));
  console.log(`${k}.json: ${fs.statSync(p).size} bytes`);
}
