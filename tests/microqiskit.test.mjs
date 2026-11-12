// Runs microqiskit.py on the real MicroPython (WebAssembly) and compares it with the JS core.
import fs from 'fs'; import path from 'path'; import { createRequire } from 'module'; import assert from 'assert';
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const Q = createRequire(import.meta.url)('../src/core.js');
const M = await import(root + '/vendor/micropython/micropython.mjs');
const out = [];
const mp = await M.loadMicroPython({ url: root + '/vendor/micropython/micropython.wasm', heapsize: 16 << 20, stdout: l => out.push(l), stderr: l => out.push('E:' + l) });
mp.FS.mkdir('/lib'); mp.FS.writeFile('/lib/microqiskit.py', fs.readFileSync(root + '/src/microqiskit.py', 'utf8'));
mp.runPython('import sys\nsys.path.append("/lib")');
const run = code => { out.length = 0; mp.runPython(code); return out.join('\n'); };
let n = 0; const t = (name, fn) => { try { fn(); n++; } catch (e) { console.log('FAIL', name, e.message); process.exitCode = 1; } };
const near = (a, b, e = 1e-6) => assert(Math.abs(a - b) < e, a + ' vs ' + b);
const progs = {
  bell: 'H-X#0\nI-X#1', ghz: 'H-X#0-I\nI-X#1-X#0\nI-I-X#1', hzh: 'H-Z-H', rot: 'H-RZ(pi/3)-RX(pi/2)-P(pi/4)\nI-I-I-I', toff: 'X-X#0\nX-X#1\nI-X#2', swap: 'X-SWAP#0-H\nI-SWAP#1-I',
  cp: 'H-P(pi/2)#0-H\nH-P(pi/2)#1-I', sx: 'SX-SXD-S-SD-T-TD\nI-I-I-I-I-I', y: 'Y-H-Y-H#0\nI-I-I-H#1'
};
// python probabilities (qiskit order: qubit 0 on the right) vs JS core (qubit 0 on the left)
for (const [name, text] of Object.entries(progs)) t('qasm->python probs: ' + name, () => {
  const c = Q.fromText(text); const qasm = Q.toQasm(c); const res = Q.simulate(c);
  const py = run('from microqiskit import from_qasm, simulate\nimport json\nqc = from_qasm(' + JSON.stringify(qasm) + ')\nprint(json.dumps(simulate(qc, 1, "probabilities")))');
  const got = JSON.parse(py);
  res.probs.forEach((p, i) => { const k = Q.label(i, c.n).split('').reverse().join(''); near(got[k] || 0, p); });
});
t('python qasm text matches the JS exporter', () => {
  const c = Q.fromText(progs.rot); const py = run('from microqiskit import QuantumCircuit\nfrom math import pi\nqc = QuantumCircuit(2)\nqc.h(0)\nqc.rz(pi/3, 0)\nqc.rx(pi/2, 0)\nqc.p(pi/4, 0)\nprint(qc.qasm())');
  assert.equal(py, Q.toQasm(c));
});
t('counts and bit order', () => {
  const py = run('from microqiskit import *\nqc = QuantumCircuit(2, 2)\nqc.x(0)\nqc.measure(0, 0)\nqc.measure(1, 1)\nprint(simulate(qc, 10, "counts"))');
  assert.equal(py, "{'01': 10}");
});
t('bell counts', () => {
  const py = run('from microqiskit import *\nqc = QuantumCircuit(2)\nqc.h(0)\nqc.cx(0, 1)\nc = simulate(qc, 1000, "counts", 5)\nprint(sorted(c.keys()), c["00"] > 400, c["11"] > 400)');
  assert.equal(py, "['00', '11'] True True");
});
t('statevector', () => { const py = run('from microqiskit import *\nqc = QuantumCircuit(1)\nqc.h(0)\nqc.s(0)\nsv = simulate(qc, 1, "statevector")\nprint(round(sv[0].real,4), round(sv[1].imag,4))'); assert.equal(py, '0.7071 0.7071'); });
t('draw', () => { const py = run('from microqiskit import *\nqc = QuantumCircuit(2)\nqc.h(0)\nqc.cx(0, 1)\nprint(qc.draw())'); assert(py.includes('[H]') && py.includes('\u25cf') && py.includes('(+)') && py.includes('\u2502'), py); });
t('draw equals JS diagram', () => { const c = Q.fromText('H-X#0-RZ(pi/2)\nI-X#1-I'); const js = Q.toDiagram(c); const py = run('from microqiskit import *\nfrom math import pi\nqc = QuantumCircuit(2)\nqc.h(0)\nqc.cx(0, 1)\nqc.rz(pi/2, 0)\nprint(qc.draw())'); assert.equal(py, js); });
t('errors are friendly', () => {
  assert(/does not exist/.test(run('from microqiskit import *\ntry:\n    QuantumCircuit(1).h(3)\nexcept ValueError as e:\n    print(e)')));
  assert(/does not support/.test(run('from microqiskit import *\ntry:\n    from_qasm("qubit[1] q;\\nfor int i in [0:2] { h q[i]; }")\nexcept ValueError as e:\n    print(e)')));
  assert(/Make the circuit with/.test(run('from microqiskit import *\ntry:\n    QuantumCircuit(1).measure(0, 0)\nexcept ValueError as e:\n    print(e)')));
});
t('last()', () => { assert.equal(run('import microqiskit as m\nqc = m.QuantumCircuit(3)\nprint(m.last().num_qubits)'), '3'); });
console.log(n + ' microqiskit tests ok');
