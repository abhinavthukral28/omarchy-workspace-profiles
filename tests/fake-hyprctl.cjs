// Compositor boundary only: never executes user commands or contacts sockets.
const fs = require('node:fs');
const args = process.argv.slice(2);
const file = process.env.TEST_CLIENTS;
const state = JSON.parse(fs.readFileSync(file, 'utf8'));
if (args[0] === 'clients') console.log(JSON.stringify(state.clients));
else if (args[0] === 'activeworkspace') console.log(JSON.stringify({id: state.workspace}));
else if (args[0] === 'dispatch') {
  fs.appendFileSync(process.env.TEST_LOG, JSON.stringify(args) + '\n');
  if (!/^hl\.dsp\.exec_cmd\(/.test(args[1])) throw Error('Unsafe/unexpected dispatch');
  const ws = args[1].match(/\[workspace (\d+) silent\]/);
  if (!ws) throw Error('Missing explicit workspace');
  if (process.env.TEST_GATE) {
    fs.writeFileSync(process.env.TEST_GATE + '.entered', '');
    while (!fs.existsSync(process.env.TEST_GATE)) Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 10);
  }
  if (!process.env.TEST_NO_WINDOW) {
    for (let i=0; i < (process.env.TEST_EXTRA_WINDOW ? 2 : 1); i++) {
      state.clients.push({address: '0x' + (state.clients.length + 100).toString(16), pid: 999,
        class: process.env.TEST_NEW_CLASS || 'new-app', initialClass: process.env.TEST_NEW_CLASS || 'new-app',
        workspace: {id: Number(ws[1])}});
    }
    fs.writeFileSync(file, JSON.stringify(state));
  }
  console.log('ok');
} else throw Error('Unexpected fake hyprctl: ' + args.join(' '));
