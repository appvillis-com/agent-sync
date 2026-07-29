#!/usr/bin/env node
'use strict';

/**
 * agent-sync installer. Zero dependencies.
 *
 * One channel per agent: Claude Code gets the plugin, every other agent gets the
 * skill through the vercel skills CLI, and the plain ~/.claude/skills/agent-sync
 * copy that the skills CLI recreates on its own is pruned afterwards — that
 * duplicate shadows the plugin and silently serves a stale skill.
 */

const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const REPO = 'appvillis-com/agent-sync';
const NAME = 'agent-sync';
const SHADOW = path.join(os.homedir(), '.claude', 'skills', NAME);

const C = {
  dim: (s) => `\x1b[2m${s}\x1b[0m`,
  bold: (s) => `\x1b[1m${s}\x1b[0m`,
  green: (s) => `\x1b[32m${s}\x1b[0m`,
  yellow: (s) => `\x1b[33m${s}\x1b[0m`,
  red: (s) => `\x1b[31m${s}\x1b[0m`,
};

function run(cmd, args) {
  process.stdout.write(C.dim(`  $ ${cmd} ${args.join(' ')}\n`));
  const r = spawnSync(cmd, args, { stdio: 'inherit' });
  return r.status === 0;
}

function has(cmd) {
  return spawnSync(process.platform === 'win32' ? 'where' : 'which', [cmd], {
    stdio: 'ignore',
  }).status === 0;
}

function usage() {
  console.log(`
${C.bold('agent-sync')} — coordination for concurrent agents

  npx ${NAME} install              install for Claude Code and other agents
  npx ${NAME} install --claude-only  Claude Code plugin only
  npx ${NAME} install --agent a,b    pick agents for the skills CLI
  npx ${NAME} --help

After installing, initialise the project — this is the step that asks where
coordination state should live:

  ${C.bold('/agent-sync init')}

It writes .claude/agent-sync.json (committed) and .env.agent-sync (gitignored,
mode 600), then tells you the one thing only you can do: create an API token in
your own knowledge-base instance and paste it into that file. The installer never
asks for a token and never stores one.
`);
}

function install(argv) {
  const claudeOnly = argv.includes('--claude-only');
  const noClaude = argv.includes('--no-claude');
  const agentIdx = argv.indexOf('--agent');
  const agents = agentIdx !== -1 && argv[agentIdx + 1] ? argv[agentIdx + 1].split(',') : null;

  let ok = true;

  if (!noClaude) {
    console.log(C.bold('\nClaude Code — as a plugin'));
    if (!has('claude')) {
      console.log(C.yellow('  claude CLI not found; skipping the plugin channel'));
    } else {
      // The full <name>@<name> form is required; `claude plugin install agent-sync`
      // answers "Plugin not found".
      ok = run('claude', ['plugin', 'marketplace', 'add', REPO]) && ok;
      ok = run('claude', ['plugin', 'install', `${NAME}@${NAME}`]) && ok;
    }
  }

  if (!claudeOnly) {
    console.log(C.bold('\nOther agents — via the skills CLI'));
    const args = ['--yes', 'skills', 'add', REPO, '--global', '--yes'];
    for (const a of agents || []) args.push('--agent', a);
    ok = run('npx', args) && ok;
  }

  // Prune the shadow the skills CLI recreates even when claude-code was not targeted.
  if (!noClaude && fs.existsSync(SHADOW)) {
    fs.rmSync(SHADOW, { recursive: true, force: true });
    console.log(C.dim(`\n  pruned duplicate ${SHADOW}`));
  }

  console.log(
    ok
      ? C.green('\n✓ installed')
      : C.red('\n✗ at least one channel failed — see the output above')
  );
  console.log(`
${C.bold('Next:')} restart Claude Code, then run ${C.bold('/agent-sync init')} in your project.
It will ask where coordination state should live before writing anything.
`);
  return ok ? 0 : 1;
}

const argv = process.argv.slice(2);
if (argv.length === 0 || argv.includes('--help') || argv.includes('-h')) {
  usage();
  process.exit(0);
}
if (argv[0] === 'install') process.exit(install(argv.slice(1)));
usage();
process.exit(1);
