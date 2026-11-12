"""Browser test of the composer: tap to build, code tabs both ways, Python (MicroPython wasm) round trip, console, levels."""
import json, os, subprocess, sys, tempfile
from playwright.sync_api import sync_playwright

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import build

shots = sys.argv[1] if len(sys.argv) > 1 else "/tmp/qwl-shots"
os.makedirs(shots, exist_ok=True)
fails = []


def check(c, msg):
    print(("ok   " if c else "FAIL ") + msg)
    if not c:
        fails.append(msg)


def page(b, cfg, name, python=True):
    p = os.path.join(tempfile.gettempdir(), "qwl_%s.html" % name)
    open(p, "w", encoding="utf-8").write(build.build_html(cfg, python=python))
    pg = b.new_page(viewport={"width": 392, "height": 860}, device_scale_factor=2)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.add_init_script("window.lilith={complete:function(){window.__done=(window.__done||0)+1}}")
    pg.goto("file://" + p)
    pg.wait_for_timeout(500)
    return pg, errs


def cell(pg, r, c):
    pg.click('.cell[data-r="%d"][data-c="%d"]' % (r, c))


def gate(pg, g):
    pg.click('.gb[data-g="%s"]' % g)


with sync_playwright() as p:
    b = p.chromium.launch()
    pg, errs = page(b, {"qubits": 2, "steps": 6, "codeOpen": True}, "play")
    # composer
    gate(pg, "h"); cell(pg, 0, 0); gate(pg, "cx"); cell(pg, 0, 1)
    check("target" in pg.inner_text("#tip") or "other qubit" in pg.inner_text("#tip") or "Now tap" in pg.inner_text("#tip"), "composer: CNOT asks for the target")
    cell(pg, 1, 1); pg.wait_for_timeout(200)
    t = pg.inner_text("#rbody")
    check("50%" in t and "00" in t and "11" in t, "composer: Bell state chances")
    pg.click('#ctabs .chip[data-c="python"]'); pg.wait_for_timeout(100)
    check("qc.h(0)" in pg.input_value("#code") and "qc.cx(0, 1)" in pg.input_value("#code"), "code: Python (MicroQiskit) is generated")
    pg.click('#ctabs .chip[data-c="qasm"]'); pg.wait_for_timeout(100)
    check("cx q[0], q[1];" in pg.input_value("#code") and "OPENQASM 3.0;" in pg.input_value("#code"), "code: OpenQASM is generated")
    pg.click('#ctabs .chip[data-c="ascii"]'); pg.wait_for_timeout(100)
    a = pg.inner_text("#code")
    check("[H]" in a and "●" in a and "(+)" in a, "code: ASCII diagram")
    pg.click("#uni"); pg.wait_for_timeout(100)
    check("@" in pg.inner_text("#code") and "●" not in pg.inner_text("#code"), "code: plain ASCII toggle")
    # edit OpenQASM -> circuit
    pg.click('#ctabs .chip[data-c="qasm"]')
    pg.fill("#code", 'OPENQASM 3.0;\nqubit[3] q;\nh q[0];\ncx q[0], q[1];\ncx q[1], q[2];'); pg.click("#apply"); pg.wait_for_timeout(300)
    check(pg.locator(".row").count() == 3, "qasm edit: circuit has 3 qubits")
    check("000" in pg.inner_text("#rbody") and "111" in pg.inner_text("#rbody"), "qasm edit: GHZ chances")
    pg.fill("#code", "qubit[1] q;\nfor int i in [0:2] { h q[i]; }"); pg.click("#apply"); pg.wait_for_timeout(100)
    check("does not support" in pg.inner_text("#cmsg"), "qasm edit: friendly error for unsupported syntax")
    # Q text
    pg.click('#ctabs .chip[data-c="text"]'); pg.fill("#code", "H-RZ(pi/2)-H"); pg.click("#apply"); pg.wait_for_timeout(300)
    check(pg.locator(".row").count() == 1 and "50%" in pg.inner_text("#rbody"), "text edit: RZ circuit applied")
    # python round trip on the real MicroPython
    pg.click('#ctabs .chip[data-c="python"]')
    pg.fill("#code", "from microqiskit import QuantumCircuit, simulate\nqc = QuantumCircuit(2, 2)\nqc.h(0)\nqc.cx(0, 1)\nqc.measure(0, 0)\nqc.measure(1, 1)\nprint(simulate(qc, 200, 'counts', 3))")
    pg.click("#apply"); pg.wait_for_function("document.querySelector('#cmsg') && document.querySelector('#cmsg').textContent.length > 0", timeout=20000)
    check("Ran fine" in pg.inner_text("#cmsg"), "python: MicroQiskit ran (%s)" % pg.inner_text("#cmsg")[:80])
    check("'00'" in pg.inner_text("#pout") and "'11'" in pg.inner_text("#pout"), "python: print output shown")
    check(pg.locator(".row").count() == 2 and pg.locator(".g.meas").count() == 2, "python: circuit above follows the code (with measurements)")
    pg.fill("#code", "from microqiskit import QuantumCircuit\nqc = QuantumCircuit(1)\nqc.h(5)"); pg.click("#apply"); pg.wait_for_function("document.querySelector('#cmsg').textContent.length > 0 && document.querySelector('#cmsg').textContent.indexOf('Ran') < 0", timeout=20000)
    check("does not exist" in pg.inner_text("#cmsg"), "python: friendly error (%s)" % pg.inner_text("#cmsg")[:80])
    # undo/redo/erase/inspect/shots
    pg.click("#undo"); pg.click("#redo"); pg.click("#clr"); pg.wait_for_timeout(100)
    check(pg.locator(".g").count() == 0, "clear removes everything")
    gate(pg, "x"); cell(pg, 0, 0); gate(pg, "erase"); cell(pg, 0, 0); pg.wait_for_timeout(100)
    check(pg.locator(".g").count() == 0, "erase removes a gate")
    gate(pg, "rx"); pg.fill("#angin", "pi"); pg.press("#angin", "Enter"); pg.click('.chip[data-a="pi"]'); cell(pg, 0, 0); pg.wait_for_timeout(200)
    check("100%" in pg.inner_text("#rbody"), "rotation gate with an angle")
    pg.click('#rtabs .chip[data-t="inspect"]'); pg.wait_for_timeout(100)
    check("phase" in pg.inner_text("#rbody") and pg.locator(".bl").count() >= 1, "inspect panel with phase and Bloch discs")
    pg.click('#rtabs .chip[data-t="shots"]'); pg.click("#rs"); pg.wait_for_timeout(100)
    check("1024 shots" in pg.inner_text("#rbody"), "shots with a seed")
    # console
    for cmd in ("new 3", "h 0", "cx 0 1", "cx 1 2", "explain", "banana", "h 9", "shots 20", "undo", "python"):
        pg.fill("#cmd", cmd); pg.click("#go"); pg.wait_for_timeout(120)
    o = pg.inner_text("#out")
    check("Entangled" in o and "do not know" in o and "qubits 0 to 2" in o and "Measured 20" in o and "Undone" in o and "qc.cx(0, 1)" in o, "console: commands, explain and friendly errors")
    pg.screenshot(path=os.path.join(shots, "play.png"), full_page=True)
    check(not errs, "no page errors " + str(errs[:2]))
    pg.close()
    # levels
    lv = {"title": "Levels", "qubits": 2, "steps": 5, "complete": "all", "levels": [
        {"title": "Flip", "intro": "Make |1>.", "start": "I-I-I-I-I", "goal": {"probs": [{"state": "1", "min": 0.99}]}, "solution": "X-I-I-I-I", "hint": "X"},
        {"title": "Bell", "intro": "Make a Bell pair.", "start": "I-I-I-I-I\nI-I-I-I-I", "goal": {"probs": [{"state": "00", "approx": .5}, {"state": "11", "approx": .5}], "linked": True}, "solution": "H-X#0-I-I-I\nI-X#1-I-I-I"}]}
    pg, errs = page(b, lv, "levels")
    gate(pg, "x"); cell(pg, 0, 0); pg.wait_for_timeout(200)
    check("Solved" in pg.inner_text("#status"), "level 1 solves by tapping")
    pg.click("#next"); pg.wait_for_timeout(200)
    check("Level 2 of 2" in pg.inner_text("#lt"), "next level")
    pg.click("#solbtn"); pg.click("#loadsol"); pg.wait_for_timeout(300)
    check("Solved" in pg.inner_text("#status") and pg.evaluate("window.__done||0") >= 1, "level 2: solution loads, completion fires")
    check(not errs, "levels: no page errors " + str(errs[:2]))
    pg.close()
    pg, errs = page(b, {"qubits": 1, "codeOpen": True}, "nopy", python=False)
    pg.click('#ctabs .chip[data-c="python"]'); pg.click("#apply"); pg.wait_for_timeout(200)
    check("not available" in pg.inner_text("#cmsg"), "no-python build degrades gracefully")
    check(not errs, "nopy: no page errors")
    b.close()
print("FAILS", fails)
sys.exit(1 if fails else 0)
