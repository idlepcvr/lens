"""LENS /position — full port of Prism's Position page.

Entry + direction → the whole trade laid out, long AND short side-by-side:
sizing levels, account-impact calculations, Kelly/risk rules, ruin math, the
8h expected range and the risk read. Goal params come from saved config; the
"Override risk inputs" panel (and the Hedge/Prop preset) let you size for either
book without touching the dashboard — that's the hedge↔prop differentiation.

Backend: POSTs the merged payload to BOTH /api/goal (model outputs) and
/api/position (sizing). Long/short columns are derived client-side from the
goal's underlying move %, exactly like Prism did.
"""

import json

from .theme import shell

_CSS = r"""<style>
.pz{max-width:1040px;margin:0 auto;padding:6px 14px 60px}
.pz h1{font-family:var(--mono);font-size:13px;letter-spacing:.15em;color:var(--accent);text-transform:uppercase;margin-bottom:3px}
.pz .sub{color:var(--dim);font-size:13px;margin-bottom:16px}
.pz form{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:15px 17px;margin-bottom:18px}
.pz .frow{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:11px;margin-bottom:11px}
.pz .lf{display:flex;flex-direction:column;gap:4px}
.pz .lf label{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--dim)}
.pz .lf input{background:var(--panel2);border:1px solid var(--line2);color:var(--ink);padding:7px 10px;border-radius:6px;font-family:var(--mono);font-size:13px}
.pz .lf input:focus{outline:none;border-color:var(--accent)}
.pz .seg{display:flex;border:1px solid var(--line2);border-radius:6px;overflow:hidden}
.pz .seg button{flex:1;background:var(--panel2);color:var(--dim);border:0;padding:7px 0;font-family:var(--mono);font-size:12px;font-weight:700;text-transform:uppercase;cursor:pointer}
.pz .seg button.on.long{background:rgba(31,217,137,.16);color:var(--long)}
.pz .seg button.on.short{background:rgba(255,84,104,.16);color:var(--short)}
.pz .seg button.on.book{background:var(--accent-d);color:var(--accent)}
.pz .adv{border-top:1px dashed var(--line2);margin-top:6px;padding-top:11px}
.pz .adv.hide{display:none}
.pz .hint{font-size:10px;color:var(--dim);font-weight:600}
.pz .err{margin:0 0 14px;padding:10px 14px;border:1px solid var(--short);background:rgba(255,84,104,.08);color:var(--short);border-radius:8px;font-size:12px}
.pz .err.hide{display:none}
.pz .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.pz .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 17px}
.pz .ct{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.18em;color:var(--dim);padding-bottom:8px;border-bottom:1px solid var(--line);margin-bottom:6px}
.pz .r3{display:grid;grid-template-columns:1.1fr 1fr 1fr;gap:6px;padding:5px 0;border-bottom:1px solid var(--line);font-size:12px;align-items:baseline}
.pz .r3:last-child{border-bottom:0}
.pz .rl{color:var(--dim)}
.pz .rv{font-family:var(--mono);font-weight:600;color:var(--ink);text-align:right}
.pz .rv2{font-family:var(--mono);color:var(--dim);text-align:right}
.pz .g{color:var(--long)!important} .pz .r{color:var(--short)!important} .pz .a{color:var(--amber)!important} .pz .ac{color:var(--accent)!important} .pz .dim{color:var(--dim)!important}
.pz .empty{text-align:center;padding:30px;color:var(--dim);border:1px dashed var(--line2);border-radius:11px}
</style>"""
_XCSS = """<style>
.mread{margin:10px 0 2px;border-top:1px solid var(--line);padding-top:9px}
.mrh{font:600 10px/1.4 var(--mono);letter-spacing:.1em;text-transform:uppercase;
  color:var(--dim);margin-bottom:7px;display:flex;justify-content:space-between;gap:8px}
.mrh .tally{letter-spacing:0;text-transform:none}
.mr{display:grid;grid-template-columns:auto 1fr auto;gap:9px;align-items:baseline;
  padding:5px 0;font:400 11px/1.4 var(--mono);border-bottom:1px solid var(--line)}
.mr:last-child{border-bottom:none}
.mr .n{color:var(--dim);white-space:nowrap}
.mr .v{font-weight:600;color:var(--ink);text-align:right;white-space:nowrap}
.mr .t{font-size:10px}
.mr.bull .t{color:var(--long)} .mr.bear .t{color:var(--short)} .mr.flat .t{color:var(--dim)}
/* The veto asks rather than refuses. A blocked entry is the most interesting
   signal in the system — he has seen something the rules do not encode — and
   refusing it just moves the trade to his phone where nothing can measure it. */
.ovr{border:1px solid var(--amber-d);border-radius:6px;padding:10px 12px;margin-bottom:12px}
.ovrh{font:600 11px/1.4 var(--mono);color:var(--amber);margin-bottom:8px}
.ovr textarea{width:100%;background:var(--panel2);border:1px solid var(--line2);
  border-radius:6px;color:var(--ink);font:400 12px/1.5 var(--mono);padding:8px 10px;resize:vertical}
.ovr textarea:focus{outline:none;border-color:var(--accent)}
.ovrn{font:400 10px/1.5 var(--mono);color:var(--dim);margin-top:6px}
/* Working orders — what is actually resting on the exchange, as opposed to what
   the ticket above proposes. The two were never shown side by side, which is
   how the planned levels came to be read as the real ones. */
.ords{border:1px solid var(--line);border-radius:6px;padding:10px 12px;margin-bottom:12px}
.ordh{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
.ord{display:grid;grid-template-columns:auto 1fr auto auto;gap:10px;align-items:baseline;
  padding:7px 0;border-bottom:1px solid var(--line);font:400 12px/1.3 var(--mono)}
.ord:last-child{border-bottom:none}
.ord .role{font-weight:600}
.ord.tp .role{color:var(--long)}
.ord.sl .role{color:var(--short)}
.ord.entry .role{color:var(--accent)}
.ord .meta{color:var(--dim);font-size:11px}
.ord .px{font-weight:600;color:var(--ink);text-align:right}
.ord button{background:none;border:1px solid var(--line);border-radius:4px;color:var(--dim);
  font:600 10px/1 var(--mono);padding:5px 8px;cursor:pointer}
.ord button:hover{color:var(--short);border-color:var(--short)}
.ordnone{font:400 11px/1.6 var(--mono);color:var(--dim)}
.si.grow{margin-left:auto;justify-content:flex-end}
.strip{gap:12px var(--s5)}
/* ── Polish pass 2026-08-21 ────────────────────────────────────────────────
   Interaction states, touch targets and motion. Measured findings first:
   --faint reads 2.3:1 on these surfaces, so every label, hint and column
   header moved to --dim (5.5:1+). --faint is now decoration only. */

/* Focus was invisible everywhere — a keyboard user had no idea where they
   were, on a page whose buttons spend money. */
.term-l button:focus-visible,.dial-b .xp:focus-visible,.xgo:focus-visible,
.xcl:focus-visible,.ghost button:focus-visible,.xdlg button:focus-visible,
.dseg button:focus-visible,.oseg .xp:focus-visible,.bseg .xp:focus-visible{
  outline:2px solid var(--accent);outline-offset:2px}
.term-l input:focus-visible,.term-l select:focus-visible{
  outline:2px solid var(--accent);outline-offset:1px;border-color:var(--accent)}
.xchk input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* One motion vocabulary: 150ms, ease-out, state only. */
.dseg button,.oseg .xp,.bseg .xp,.xgo,.xcl,.ghost button,.dial-b .xp{
  transition:background-color .15s cubic-bezier(.22,1,.36,1),
             border-color .15s cubic-bezier(.22,1,.36,1),
             color .15s cubic-bezier(.22,1,.36,1)}
.xgo:hover:not(:disabled),.xcl:hover:not(:disabled){filter:brightness(1.12)}
.dseg button:not(.on):hover,.oseg .xp:not(.on):hover,.bseg .xp:not(.on):hover{color:var(--ink);border-color:var(--line2)}
.xgo:active:not(:disabled),.xcl:active:not(:disabled),
.dial-b .xp:active,.dseg button:active,.oseg .xp:active,.bseg .xp:active{transform:translateY(1px)}

/* Phone is the daily driver per PRODUCT.md, so touch targets get the 44px
   minimum on coarse pointers — they were 34–38px. */
@media (pointer:coarse){
  .dial-b .xp,.dseg button,.oseg .xp,.bseg .xp{min-height:44px}
  .xgo,.xcl{min-height:44px;padding-top:0;padding-bottom:0}
  .term-l input,.term-l select{min-height:44px}
  .xchk{padding:var(--s1) 0}
  .dial-r{height:28px}
}

/* The ledger sets its own column widths; below them it must scroll itself
   rather than push the page sideways. */
.tw{overflow-x:auto}

.xdlg{opacity:0;transform:translateY(6px) scale(.99);
  transition:opacity .16s ease-out,transform .16s cubic-bezier(.22,1,.36,1)}
.xdlg[open]{opacity:1;transform:none}
.xdlg::backdrop{opacity:0;transition:opacity .16s ease-out}
.xdlg[open]::backdrop{opacity:1}

@media (prefers-reduced-motion:reduce){
  .dseg button,.oseg .xp,.bseg .xp,.xgo,.xcl,.ghost button,.dial-b .xp,.xdlg,.xdlg::backdrop{
    transition:none}
  .xgo:active,.xcl:active,.dial-b .xp:active,.dseg button:active,.oseg .xp:active,.bseg .xp:active{
    transform:none}
  .xdlg{opacity:1;transform:none}
}
/* No inner scrollbar. The left column is sticky, not a scroll region — a panel
   that scrolls inside a page that also scrolls is two scrollbars and one
   confused thumb. */
.term-l .xw{border:0;background:transparent;padding:0;margin:0}

/* Direction and order type: full-width segmented controls, and the plain .on
   state actually has a style now — it inherited nothing, which is why Market /
   Limit highlighting looked broken. */
.dseg,.oseg,.bseg{display:grid;grid-template-columns:1fr 1fr;gap:0;margin-bottom:14px}
.dseg button,.oseg .xp,.bseg .xp{padding:11px 0;font:700 12px/1 var(--mono);text-transform:uppercase;
  background:var(--panel2);color:var(--dim);border:1px solid var(--line2);cursor:pointer}
.dseg button:first-child,.oseg .xp:first-child,.bseg .xp:first-child{border-radius:6px 0 0 6px}
.dseg button:last-child,.oseg .xp:last-child,.bseg .xp:last-child{border-radius:0 6px 6px 0;border-left:0}
.oseg .xp.on,.bseg .xp.on{background:var(--accent);border-color:var(--accent);color:var(--bg)}
.dseg button.on.long{background:var(--long);border-color:var(--long);color:var(--bg)}
.dseg button.on.short{background:var(--short);border-color:var(--short);color:var(--bg)}

.xchk{align-items:flex-start;line-height:1.45}
.hint2{display:block;font:400 11px/1.5 var(--mono);color:var(--dim);
  text-transform:none;letter-spacing:0;margin-top:3px}
.xcl.sm{padding:5px 10px;font-size:10px}

/* Confirm dialog. Native <dialog>: Esc and the backdrop come free. */
/* ROOT CAUSE of the top-left dialog: lens.css carries
   `*,*::before,*::after{margin:0}`, and that universal reset zeroes the margin
   on <dialog> as well — which is exactly the `margin:auto` the browser uses to
   centre a modal. Restating it here wins on specificity (.xdlg beats *).
   Do not "simplify" this away; the reset will silently un-centre it again. */
.xdlg{position:fixed;inset:0;margin:auto;height:fit-content;
  max-height:calc(100dvh - 32px);overflow:auto;
  border:1px solid var(--line);border-radius:11px;background:var(--panel);
  color:var(--ink);padding:0;width:min(440px,calc(100vw - 32px));max-width:none}
.xdlg::backdrop{background:rgba(3,5,9,.72)}
.xdlg .dh{display:flex;justify-content:space-between;align-items:center;gap:10px;
  padding:15px 18px;border-bottom:1px solid var(--line);
  font:700 12px/1 var(--mono);letter-spacing:.16em;text-transform:uppercase}
.dlead{padding:16px 18px 4px;font:700 21px/1.2 var(--mono);color:var(--ink)}
.dlead.long{color:var(--long)} .dlead.short{color:var(--short)}
.xdlg .xdetail{border:0;border-radius:0;margin:0;padding:10px 18px 4px}
.dwarn{padding:10px 18px 0;font:400 11px/1.6 var(--mono);color:var(--dim)}
.dwarn.live{color:var(--short)}
.dbtns{display:flex;gap:10px;justify-content:flex-end;padding:16px 18px 18px}
.dbtns .xgo,.dbtns .xcl{padding:10px 20px}
.tl .p i{font-style:normal;font-size:11px;margin-left:6px}
.tl .p i.ok{color:var(--long)}
.tl .p i.no{color:var(--dim)}
.legend i{font-style:normal}
.legend i.ok{color:var(--long)}
.legend i.no{color:var(--dim)}
/* Vertical rhythm. One spacing step between groups in the ticket, so the eye
   can find the next control instead of parsing a wall. */
.term-l .xrow{margin-bottom:16px}
.term-l .frow{margin-bottom:16px}
.ghost{margin:-6px 0 16px}
.xchk{margin-bottom:12px}
#x-tpslbox{margin-bottom:4px}
.xdetail{margin-top:4px}

/* The dial is its own control, not a segmented button group. Borrowing .seg
   forced flex:1 onto every child and glued them edge to edge inside a border. */
.dial{margin:0 0 18px}
.dial-h{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
.dial-v{font:600 13px/1 var(--mono);color:var(--ink)}
.dial-b{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px}
.dial-b .xp{background:var(--panel2);border:1px solid var(--line2);color:var(--dim);
  border-radius:6px;padding:8px 0;font:600 11px/1 var(--mono);cursor:pointer;
  transition:background .15s ease-out,color .15s ease-out,border-color .15s ease-out}
.dial-b .xp:hover{color:var(--ink);border-color:var(--dim)}
.dial-b .xp.on{background:var(--accent);border-color:var(--accent);color:var(--bg)}
.dial-r{display:block;width:100%;accent-color:var(--accent);margin:0}
@media (prefers-reduced-motion:reduce){.dial-b .xp{transition:none}}
/* Dense ledger rows. Seven columns on desktop; the two derived percentage
   columns fold away on a phone, where price / € / balance are what you check. */
.tl{display:grid;grid-template-columns:minmax(74px,1fr) 96px 62px 62px 66px 74px;
  gap:10px;align-items:baseline;padding:9px 0;border-bottom:1px solid var(--line);
  font:400 12px/1.3 var(--mono);white-space:nowrap}
.tl:last-of-type{border-bottom:none}
.tl .k{color:var(--dim)}
.tl .p{font-weight:600;color:var(--ink);font-size:14px;text-align:right}
.tl .mk,.tl .ac,.tl .m,.tl .a{text-align:right;color:var(--dim);font-size:11px}
.tl .m{font-weight:600}
.tl.th{border-bottom:1px solid var(--line);padding-bottom:6px}
.tl.th span{font:400 10px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--dim)}
.tl.tp .p,.tl.tp .m,.tl.tp .ac,.tl.tp .mk{color:var(--long)}
.tl.sl .p,.tl.sl .m,.tl.sl .ac,.tl.sl .mk{color:var(--short)}
.tl.liq .p{color:var(--amber)}
.tl.en .p{color:var(--accent)}
.tw .ct{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
.tw .ct .rr{color:var(--dim);letter-spacing:0;text-transform:none;font-weight:400}
.risk{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;
  margin-top:13px;padding-top:12px;border-top:1px solid var(--line);
  font:400 12px/1.5 var(--mono);color:var(--dim)}
.risk b{font-weight:600}
.risk .good{color:var(--long)} .risk .good b{color:var(--long)}
.risk .warn{color:var(--amber)} .risk .warn b{color:var(--amber)}
.risk .bad{color:var(--short)} .risk .bad b{color:var(--short)}
.risk .rec{color:var(--dim)}
.legend{margin-top:11px;font:400 11px/1.7 var(--mono);color:var(--dim)}
@media (max-width:620px){
  .tl{grid-template-columns:minmax(64px,1fr) 92px 62px 66px}
  .tl .mk,.tl .ac,.tl.th .mk,.tl.th .ac{display:none}
}
/* One form vocabulary. The sizing inputs and the order inputs were two
   different control styles stacked in one column, which is what read as
   "weird" — same shape, same padding, same surface, or one of them is wrong. */
.term-l .lf input,.term-l .xf input,.term-l .xf select{
  background:var(--panel2);border:1px solid var(--line2);color:var(--ink);
  padding:8px 10px;border-radius:6px;font:600 13px/1.2 var(--mono);width:100%}
.term-l .lf input:focus,.term-l .xf input:focus,.term-l .xf select:focus{
  outline:none;border-color:var(--accent)}
.term-l .lf label,.term-l .xf label{
  font:400 9px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--dim)}

/* In a 380px column, two-up is the honest maximum. */
.term-l .frow{grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}
.term-l .xrow{display:grid;grid-template-columns:1fr 1fr;gap:10px;align-items:end}
.term-l .xrow .xf{min-width:0}
.term-l .xrow.one{grid-template-columns:1fr}
.term-l .xs{min-width:0}

/* The left column is ONE ticket, not two panels that happen to be adjacent. */
.term-l>form{margin:0}
.term-l .xw .xh{margin-top:0}
.term-l{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}

/* The recommendation, shown but not shouted — greyed behind what he typed. */
.ghost{font:400 11px/1.4 var(--mono);color:var(--dim);margin-top:5px}
.ghost b{color:var(--ink);font-weight:600}
.ghost button{background:none;border:0;color:var(--accent);font:600 11px/1 var(--mono);
  cursor:pointer;padding:0 0 0 6px}
/* Terminal layout. Phone-first per PRODUCT.md: one column, order form first
   because the phone is the pre-trade glance. Two columns only where there is
   room for the readout to sit beside the controls that drive it. */
.term{display:flex;flex-direction:column;gap:16px}
.term-l{display:flex;flex-direction:column;min-width:0}
.term-r{min-width:0}
@media (min-width:1000px){
  .term{display:grid;grid-template-columns:minmax(380px,440px) minmax(0,1fr);
        align-items:start;gap:20px}
  .term-l{position:sticky;top:14px}
}

/* Instrument strip — the one number that matters, loudest. */
.strip{display:flex;flex-wrap:wrap;gap:12px 26px;align-items:baseline;
  border:1px solid var(--line);border-radius:9px;background:var(--panel);
  padding:12px 16px;margin:0 0 16px}
.si{display:flex;flex-direction:column;gap:5px;min-width:76px}
.sl{font:400 10px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}
.sv{font:600 14px/1 var(--mono);color:var(--ink)}
.sv.hero{font-size:22px;letter-spacing:-.01em}
.sv.g{color:var(--long)}
.sv.r{color:var(--short)}

/* The trade: the levels for the size actually in the ticket. */
.tw{border:1px solid var(--line);border-radius:9px;background:var(--panel);
  padding:14px 16px;margin:0 0 16px}
.tw .ct{font:700 10px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;
  color:var(--dim);margin-bottom:12px}
.tl:last-child{border-bottom:none}
.tl .k{color:var(--dim)}
.tl .p{font-weight:600;color:var(--ink);font-size:14px}
.scaled{margin-top:11px;font:400 11px/1.6 var(--mono);color:var(--amber)}
.xw{border:1px solid var(--line);border-radius:9px;background:var(--panel);padding:14px 16px;margin:0 0 16px}
.xh{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:14px;
  padding-bottom:10px;border-bottom:1px solid var(--line)}
.xhr{display:flex;align-items:center;gap:10px}
.xt{font:700 12px/1 var(--mono);letter-spacing:.16em;text-transform:uppercase;color:var(--ink)}
.xenv{font:700 10px/1 var(--mono);letter-spacing:.14em;padding:4px 8px;border-radius:4px}
.xenv.live{background:var(--short);color:var(--bg)}
.xenv.demo{background:transparent;color:var(--dim);border:1px solid var(--line)}
.xrow{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin-bottom:12px}
.xf{display:flex;flex-direction:column;gap:5px;min-width:130px;flex:1}
.xf label{font:400 10px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}
.xf input,.xf select{background:var(--bg);border:1px solid var(--line);border-radius:6px;
  color:var(--ink);font:600 13px/1 var(--mono);padding:9px 10px;width:100%}
.xf input:focus,.xf select:focus{outline:0;border-color:var(--accent)}
.xs{display:flex;flex-direction:column;gap:5px;min-width:110px}
.xl{font:400 10px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}
.xv{font:600 13px/1 var(--mono);color:var(--ink)}
.xchk{display:flex;align-items:center;gap:7px;font:600 11px/1 var(--mono);color:var(--ink);
  cursor:pointer;margin-bottom:10px}
.xdetail{border:1px solid var(--line);border-radius:6px;padding:10px 12px;margin-bottom:12px}
.xct{font:700 10px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--dim);margin-bottom:9px}
.xd{display:flex;justify-content:space-between;gap:12px;padding:5px 0;
  font:400 12px/1.4 var(--mono);color:var(--dim);border-bottom:1px solid var(--line)}
.xd:last-child{border-bottom:none}
.xd span:last-child{color:var(--ink);font-weight:600}
.xgates{font:400 11px/1.7 var(--mono);color:var(--dim);margin-bottom:12px;
  padding:8px 10px;border:1px solid var(--line);border-radius:5px}
.xgates .no{color:var(--short)}
.xgates .yes{color:var(--long)}
.xgates .ovrf{color:var(--amber)}
.xbtns{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.xgo,.xcl{border:0;border-radius:7px;padding:10px 18px;font:700 12px/1 var(--mono);cursor:pointer}
.xgo{background:var(--long);color:var(--bg)}
.xgo.short{background:var(--short);color:var(--bg)}
.xgo:disabled,.xcl:disabled{background:transparent;color:var(--faint);border:1px solid var(--line);cursor:not-allowed}
.xcl{background:transparent;color:var(--dim);border:1px solid var(--line)}
.xmsg{font:400 11px/1.5 var(--mono);color:var(--dim)}
.xtbl{width:100%;border-collapse:collapse;font:400 12px/1 var(--mono);white-space:nowrap}
.xtbl th{font:400 10px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--dim);
  text-align:right;padding:0 0 8px;border-bottom:1px solid var(--line)}
.xtbl th:first-child,.xtbl td:first-child{text-align:left}
.xtbl td{text-align:right;padding:9px 0;border-bottom:1px solid var(--line);color:var(--ink)}
.xtbl td.g{color:var(--long)}
.xtbl td.r{color:var(--short)}
.xtbl th+th,.xtbl td+td{padding-left:16px}
</style>"""




def position_page(book: str = "hedge") -> str:
    sub = ('Entry → full trade: levels, sizing, risk — long &amp; short. Sized off <b>live eval equity</b> '
           'at the plan\'s risk — see <a href="/prop-survival#rules" style="color:var(--accent)">Rules</a>. '
           'Risk sets the <b>size</b>; leverage only sets the <b>margin</b> and the liq price — '
           'move it freely, the stop, target and € at risk don\'t budge. '
           'Override risk %, R:R or leverage below for a per-trade what-if; the saved plan is untouched.'
           if book == "prop" else
           'Entry → full trade: levels, sizing, risk — long &amp; short. Params from your '
           '<a href="/hedge-plan" style="color:var(--accent)">config</a>; override per trade or flip the book below.')
    body = r"""
<div class="pz">
  <h1>Position</h1>
  <div class="sub">""" + sub + r"""</div>

  <div class="strip" id="strip">
    <div class="si"><span class="sl">contract</span><span class="sv" id="s-sym">PF_XBTUSD</span>
      <span class="xenv" id="s-env">—</span></div>
    <div class="si"><span class="sl">mark</span><span class="sv hero" id="s-mark">—</span></div>
    <div class="si"><span class="sl">index</span><span class="sv" id="s-index">—</span></div>
    <div class="si"><span class="sl">last</span><span class="sv" id="s-last">—</span></div>
    <div class="si"><span class="sl">balance</span><span class="sv" id="s-bal">—</span></div>
    <div class="si"><span class="sl">available</span><span class="sv" id="s-avail">—</span></div>
    <div class="si"><span class="sl">open</span><span class="sv" id="s-open">—</span></div>
    <div class="si"><span class="sl">unrealised</span><span class="sv" id="s-upnl">—</span></div>
    <div class="si"><span class="sl">entry · liq</span><span class="sv" id="s-entry">—</span></div>
    <div class="si"><span class="sl">live TP</span><span class="sv g" id="s-tp">—</span></div>
    <div class="si"><span class="sl">live SL</span><span class="sv r" id="s-sl">—</span></div>
    <div class="si grow"><span class="sl">&nbsp;</span>
      <button type="button" id="s-close" class="xcl sm" onclick="askClose()" disabled>Close position</button></div>
  </div>

  <div class="term">
  <aside class="term-l">
  <div id="xbar" class="xw" style="display:none">
    <div class="xh">
      <span class="xt">Order</span>
      <span class="xhr"><span id="x-mark" class="xl">mark —</span><span id="x-env" class="xenv">—</span></span>
    </div>

    <div class="seg bseg" id="book-preset-row">
      <button type="button" id="b-hedge" class="xp on" onclick="setBook('hedge')">Hedge</button>
      <button type="button" id="b-prop" class="xp" onclick="setBook('prop')">Prop</button>
    </div>

    <div class="seg dseg">
      <button type="button" id="d-long" class="on long" onclick="setDir('long')">▲ Long</button>
      <button type="button" id="d-short" class="short" onclick="setDir('short')">▼ Short</button>
    </div>

    <!-- Daily volatility is a feed, not a decision: it sets the 8-hour move and
         nothing else, so it stays populated and out of sight. -->
    <input id="o-std" type="hidden">

    <div class="seg oseg" id="x-otype">
      <button type="button" class="xp on" onclick="setOT('mkt')">Market</button>
      <button type="button" class="xp" onclick="setOT('lmt')">Limit</button>
    </div>

    <div class="xrow">
      <div class="xf"><label id="x-pricelab">Entry price USD</label>
        <input id="p-entry" type="text" inputmode="decimal" placeholder="61900" autofocus></div>
      <div class="xf"><label>Leverage</label>
        <input id="x-lev" type="text" inputmode="decimal" value="10" oninput="calc()"></div>
    </div>

    <div class="xrow">
      <div class="xf"><label>Risk per trade %</label>
        <input id="x-risk" type="text" inputmode="decimal" oninput="calc()"></div>
      <div class="xf" id="x-tif-wrap" style="display:none"><label>Time in force</label>
        <select id="x-tif" onchange="paintExec()">
          <option value="lmt">Good till cancelled</option>
          <option value="ioc">Immediate or cancel</option>
        </select></div>
    </div>

    <div class="xrow">
      <div class="xf"><label>Quantity BTC</label><input id="x-qty" type="text" inputmode="decimal" oninput="qtyEdited()"></div>
      <div class="xf"><label>Total USD</label><input id="x-usd" type="text" inputmode="decimal" oninput="usdEdited()"></div>
    </div>
    <div class="ghost" id="x-ghost">recommended <b id="x-full">—</b> · <b id="x-recusd">—</b>
      · <b id="x-receur">—</b> · <b id="x-reclev">—</b><button type="button" onclick="useRecommended()">use</button></div>

    <div class="dial">
      <div class="dial-h"><span class="xl">size dial</span><span id="x-pctv" class="dial-v">100%</span></div>
      <div class="dial-b" id="x-pctseg">
        <button type="button" class="xp" onclick="setPct(25)">25%</button>
        <button type="button" class="xp" onclick="setPct(50)">50%</button>
        <button type="button" class="xp" onclick="setPct(75)">75%</button>
        <button type="button" class="xp on" onclick="setPct(100)">100%</button>
      </div>
      <input id="x-pct" class="dial-r" type="range" min="1" max="100" value="100" oninput="setPct(this.value,1)">
    </div>

    <label class="xchk"><input type="checkbox" id="x-tpsl" checked onchange="toggleTPSL()">
      Send a take profit and stop loss with it</label>
    <div id="x-tpslbox">
      <div class="xrow">
        <div class="xf"><label>Take profit USD</label><input id="x-tp" type="text" inputmode="decimal" oninput="paintExec()"></div>
        <div class="xf"><label>Stop loss USD</label><input id="x-sl" type="text" inputmode="decimal" oninput="paintExec()"></div>
      </div>
      <div class="xrow one">
        <div class="xf"><label>Which price triggers them</label>
          <select id="x-trig" onchange="paintExec()">
            <option value="mark">Mark price — the exchange's fair value, hardest to spike</option>
            <option value="index">Index price — the spot average across exchanges</option>
            <option value="last">Last traded price on this contract</option>
          </select>
        </div>
      </div>
    </div>

    <div class="xrow one" id="f-bal">
      <div class="xf"><label id="bal-label">Balance €</label><input id="p-bal" type="text" inputmode="decimal" placeholder="—"></div>
    </div>
    <div class="xrow one" id="f-btc">
      <div class="xf"><label>BTC price €</label><input id="p-btc" type="text" inputmode="decimal" placeholder="—"></div>
    </div>

    <div class="ords" id="x-ords">
      <div class="ordh"><span class="xl">working orders</span><span class="xl" id="ord-n">—</span></div>
      <div id="ord-list"></div>
    </div>

    <div id="x-gates" class="xgates">—</div>
    <div id="x-ovr" class="ovr" style="display:none">
      <div class="ovrh">The scanner says no. What do you see?</div>
      <textarea id="x-ovr-why" rows="2" oninput="paintExec()"
        placeholder="e.g. momentum break above 75.3k with the daily trend, FVG retrace already filled"></textarea>
      <div class="mread" id="x-mread"></div>
      <div class="ovrn" id="x-ovr-n">Recorded with the trade, so it can be checked against the outcome later.</div>
    </div>
    <div class="xbtns">
      <button type="button" id="x-go" class="xgo" onclick="askExec()">▲ Execute</button>
      <button type="button" id="x-close" class="xcl" onclick="askClose()">Close position</button>
      <button type="button" id="x-cancel" class="xcl" onclick="cancelAll()">Cancel resting</button>
      <span id="x-msg" class="xmsg"></span>
    </div>
  </div>

  </aside>

  <main class="term-r">
  <div id="err" class="err hide"></div>
  <div id="logbar" style="display:none;margin:0 0 14px;display:flex;gap:10px;align-items:center">
    <button type="button" id="logbtn" onclick="logTrade()" style="background:var(--accent);color:var(--bg);border:0;border-radius:7px;padding:9px 18px;font-family:var(--mono);font-size:12px;font-weight:700;cursor:pointer">＋ Log as open trade</button>
    <span id="logmsg" style="font-size:12px;color:var(--dim)"></span>
  </div>
  <div id="out"><div class="empty">Enter an entry price to size the trade.</div></div>
  </main>
  </div>


<dialog id="x-dlg" class="xdlg">
  <div class="dh"><span id="dlg-t">Confirm order</span><span id="dlg-env" class="xenv">—</span></div>
  <div class="dlead" id="dlg-lead">—</div>
  <div class="xdetail">
    <div class="xd"><span>Order</span><span id="d-inc">—</span></div>
    <div class="xd"><span>Take profit</span><span id="d-tp">—</span></div>
    <div class="xd"><span>Stop loss</span><span id="d-sl">—</span></div>
    <div class="xd"><span>Required margin</span><span id="d-margin">—</span></div>
    <div class="xd"><span>Available balance</span><span id="d-avail">—</span></div>
    <div class="xd"><span>Est. liquidation</span><span id="d-liq">—</span></div>
    <div class="xd"><span>Est. trading fee</span><span id="d-fee">—</span></div>
    <div class="xd"><span>Size cap</span><span id="d-cap">—</span></div>
  </div>
  <div id="dlg-warn" class="dwarn"></div>
  <div class="dbtns">
    <button type="button" class="xcl" onclick="closeDlg()">Cancel</button>
    <button type="button" id="dlg-go" class="xgo" onclick="confirmDlg()">Confirm</button>
  </div>
</dialog>
</div>"""

    script = r"""
const $=id=>document.getElementById(id);
let dir='long', book=START_BOOK, CFG=null, deb, HEDGE_BAL=null, LAST=null;
const fP=n=>n==null?'—':Number(n).toLocaleString('en',{useGrouping:false,minimumFractionDigits:2,maximumFractionDigits:2}); // ponytail: no $/commas so prices paste straight into Kraken
const fE=n=>n==null?'—':'€'+Number(n).toLocaleString('en',{minimumFractionDigits:2,maximumFractionDigits:2});
const fB=n=>n==null?'—':Number(n).toFixed(6)+' ₿';
const pc=n=>n==null?'—':Number(n).toFixed(2)+'%';

async function ensureCfg(){ if(!CFG) CFG=await fetch('/api/config').then(r=>r.json()); return CFG; }
function setDir(d){ dir=d; $('d-long').classList.toggle('on',d==='long'); $('d-short').classList.toggle('on',d==='short'); calc(); }
function setBook(b){
  book=b; $('b-hedge').classList.toggle('on',b==='hedge'); $('b-prop').classList.toggle('on',b==='prop');
  const prop = b==='prop';
  // The override panel is gone: win rate, R:R, the stop dial and the duplicate
  // leverage input were controls he never reached for, and leverage and risk
  // now live in the ticket where the order is actually built. What remains
  // book-specific is the balance field's meaning.
  $('bal-label').textContent = prop ? 'Eval balance $' : 'Balance €';
  if(!prop){
    if(HEDGE_BAL!=null) $('p-bal').value=HEDGE_BAL;
  } else {
    $('p-bal').value=''; $('p-bal').placeholder='live eval equity';
    $('x-lev').value=''; $('x-risk').value='';
  }
  calc();
}

async function calc(){
  const entry=parseFloat($('p-entry').value);
  if(!entry){ $('out').innerHTML='<div class="empty">Enter an entry price to size the trade.</div>'; $('err').classList.add('hide'); return; }
  if(book==='prop'){ return calcProp(entry); }
  const cfg=await ensureCfg();
  const bal=parseFloat($('p-bal').value)||cfg.start_balance;
  const btc=parseFloat($('p-btc').value)||cfg.btc_price_eur;
  // null-safe: the win-rate / R:R / stop overrides were removed from the UI,
  // so these ids are simply absent now and the config value stands.
  const ov=(id,lo,hi)=>{ const el=$(id); if(!el) return undefined;
    const v=parseFloat(el.value); return (isFinite(v)&&(lo==null||v>lo)&&(hi==null||v<hi))?v:undefined; };
  const payload={
    start_balance:cfg.start_balance, target_balance:cfg.target_balance, target_date:cfg.target_date,
    trades_per_week:cfg.trades_per_week, win_rate:cfg.win_rate, rr_ratio:cfg.rr_ratio, leverage:cfg.leverage,
    max_drawdown_allowed:cfg.max_drawdown_allowed, losses_allowed:cfg.losses_allowed,
    fractional_kelly:cfg.fractional_kelly, execution_fill_factor:cfg.execution_fill_factor, slippage_pct:cfg.slippage_pct,
    entry_price:entry, direction:dir, balance_eur:bal, btc_price_eur:btc, btc_std_dev:ov('o-std',0)||0.0356,
  };
  // leverage and risk are ticket fields now — one number, one place
  const wr=ov('o-wr',0,1), rr=ov('o-rr',0), lev=ov('x-lev',0.99);
  const rkPct=ov('x-risk',0,100), rk = rkPct!=null ? rkPct/100 : undefined;
  if(wr!=null)payload.win_rate=wr; if(rr!=null)payload.rr_ratio=rr; if(lev!=null)payload.leverage=lev; if(rk!=null)payload.risk_per_trade=rk;
  Object.keys(payload).forEach(k=>payload[k]==null&&delete payload[k]);
  const opt={method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)};
  try{
    const [gr,pr]=await Promise.all([fetch('/api/goal',opt),fetch('/api/position',opt)]);
    if(!gr.ok){ throw new Error((await gr.json()).detail||'goal error'); }
    if(!pr.ok){ throw new Error((await pr.json()).detail||'position error'); }
    $('err').classList.add('hide'); render(await gr.json(), await pr.json(), payload, bal, btc);
  }catch(e){ $('err').textContent=String(e.message||e); $('err').classList.remove('hide'); }
}

function sec(title, rows){
  return `<div class="card"><div class="ct">${title}</div>`+rows.map(r=>
    `<div class="r3"><span class="rl">${r[0]}</span><span class="rv ${r[3]||''}">${r[1]}</span><span class="rv2 ${r[4]||''}">${r[2]!=null?r[2]:''}</span></div>`).join('')+`</div>`;
}

function render(g, p, pl, bal, btcE){
  const e=p.entry, uw=g.underlying_win_pct/100, ul=g.underlying_loss_pct/100, lev=g.leverage;
  const tpL=e*(1+uw), slL=e*(1-ul), tpS=e*(1-uw), slS=e*(1+ul);
  const liqL=e*(1-0.5/lev), liqS=e*(1+0.5/lev);
  const gainE=bal*g.acct_gain_win/100, lossE=p.risk_eur;
  XFULL  = p.position_size_btc || 0;
  XMARK  = e;
  XLIQ   = dir==='long' ? liqL : liqS;
  XLEVELS= {long:{tp:tpL, sl:slL}, short:{tp:tpS, sl:slS}};
  $('xbar').style.display = XFULL ? 'block' : 'none';
  $('x-full').textContent   = XFULL.toFixed(6)+' ₿';
  $('x-receur').textContent = TRADE ? fE(TRADE.posEur) : '—';
  $('x-recusd').textContent = (TRADE && XMARK) ? '$'+(XFULL*XMARK).toFixed(2) : '—';
  $('x-reclev').textContent = TRADE ? TRADE.lev.toFixed(1)+'×' : '—';
  if(!$('x-qty').value || $('x-qty').dataset.auto!=='0'){ setPct(XPCT); }
  if($('x-tpsl').checked) fillLevels();
  disarm(); paintExec(); loadLive();
  const out = '';
  TRADE = {e, tpL, slL, tpS, slS, liqL, liqS, gainE, lossE, lev, bal,
           riskPct: g.risk_per_trade, kellyPct: g.optimal_risk_pct,
           winAcct: g.acct_gain_win, lossAcct: g.acct_loss_loss,
           winMkt: g.underlying_win_pct, lossMkt: g.underlying_loss_pct,
           sigma: p.std_8hr_usd, rr: g.actual_rr, typicalWin: g.typical_win,
           posEur: p.position_size_eur,
           full: p.position_size_btc || 0};
  $('out').innerHTML = tradeBlock() + '<div class="grid">'+out+'</div>';
  // Carry the PLAN, not just the ticket. Logging used to send entry/size/
  // leverage only, so trades.tp and trades.sl were NULL on every row ever
  // written — which meant a review could never ask "did it reach the target you
  // set", only "did it make money". The levels are already computed right here
  // for display; they just were not being kept.
  LAST={book:'hedge',direction:dir,entry:e,size:p.current_trade_size_btc,leverage:lev,
        tp:(dir==='long'?tpL:tpS), sl:(dir==='long'?slL:slS)};
  $('logbar').style.display='flex'; $('logmsg').textContent='';
}

async function ticket(q){
  const r=await fetch('/api/prop/position?'+q);
  if(!r.ok){ throw new Error((await r.json()).detail||'prop error'); }
  return r.json();
}

async function calcProp(entry){
  const q=new URLSearchParams({entry:entry, direction:dir});
  const ov=(id)=>{ const v=parseFloat($(id).value); return (isFinite(v)&&v>0)?v:null; };
  const bal=ov('p-bal'), rk=ov('o-risk'), rr=ov('o-rr'), lv=ov('o-lev'), st=ov('o-stop');
  if(bal)q.set('balance',bal); if(rk)q.set('risk',rk); if(rr)q.set('rr',rr); if(lv)q.set('lev',lv);
  try{
    // the strategy's ticket always renders; a stop override adds a second one beside it
    const base=await ticket(q);
    let alt=null;
    if(st){ const q2=new URLSearchParams(q); q2.set('stop',st); alt=await ticket(q2); }
    if(!bal) $('p-bal').placeholder=base.account;   // live eval equity, visible before you override
    $('err').classList.add('hide'); renderProp(base, alt);
  }catch(e){ $('err').textContent=String(e.message||e); $('err').classList.remove('hide'); }
}

const MM=0.005;   // maintenance margin — mirrors prop_scan.MM_RATE

// the four prices a ticket actually trades at, long and short
function levels(t){
  const e=t.entry, sp=t.stop_pct/100, tpp=t.tp_pct/100, lev=t.leverage;
  return {e, tpL:e*(1+tpp), slL:e*(1-sp), tpS:e*(1-tpp), slS:e*(1+sp),
          liqL:e*(1-1/lev+MM), liqS:e*(1+1/lev-MM),
          beL:e*(1+t.fee_rt_pct/100), beS:e*(1-t.fee_rt_pct/100)};
}

// The stop override, side by side with the strategy's own numbers. The point of
// the section: risk is identical in both columns — the stop is what buys the
// shorter travel to TP, and it's paid for in leverage and (unshown) win rate.
function overrideSec(t, o){
  const L=levels(o), cut=o.actual_risk_pct < o.risk_pct - 0.001;   // firm's cap ate the size
  const per=x=>fP(x.notional/100);                                  // $ per 1% move
  return sec('Stop override · levels', [
      ['', 'Long', 'Short', 'dim', 'dim'],
      ['Take profit', fP(L.tpL), fP(L.tpS), 'g','g'],
      ['Stop loss',   fP(L.slL), fP(L.slS), 'r','r'],
      ['Entry',       fP(L.e),   fP(L.e),   'ac'],
      ['Liquidation', L.liqL>0?fP(L.liqL):'none', fP(L.liqS), 'a','a'],
      ['Travel to TP', pc(o.tp_pct), 'was '+pc(t.tp_pct), 'g','dim'],
    ])
  + sec('Stop override · vs strategy', [
      ['', 'Strategy', 'Override', 'dim', 'dim'],
      ['Stop',        pc(t.stop_pct), pc(o.stop_pct), 'dim','r'],
      ['Travel to TP',pc(t.tp_pct),   pc(o.tp_pct),   'dim','g'],
      ['Notional',    fP(t.notional), fP(o.notional), 'dim','ac'],
      ['$ / 1% move', per(t),         per(o),         'dim','ac'],
      ['Leverage needed', t.min_leverage+'×', o.min_leverage+'×', 'dim', cut?'r':'a'],
      ['Margin',      pc(t.margin_pct), pc(o.margin_pct), 'dim',''],
      ['Risk / trade',pc(t.actual_risk_pct), pc(o.actual_risk_pct), 'dim', cut?'r':'g'],
      ['Win $',       fP(t.win_usd),  fP(o.win_usd),  'dim','g'],
      [cut ? '⚠ Over the '+o.max_leverage+'× cap' : 'Risk held · same €',
       cut ? 'size cut' : 'yes',
       cut ? 'floor: '+pc(o.risk_pct/o.max_leverage)+' stop' : 'shorter travel, tighter stop',
       cut?'r':'g', 'dim'],
    ]);
}

function renderProp(t, o){
  const L=levels(t), lev=t.leverage;
  const e=L.e, tpL=L.tpL, slL=L.slL, tpS=L.tpS, slS=L.slS, liqL=L.liqL, liqS=L.liqS, beL=L.beL, beS=L.beS;
  const out =
    sec('Position sizing · PROP', [
      ['', 'Long', 'Short', 'dim', 'dim'],
      ['Take profit', fP(tpL), fP(tpS), 'g','g'],
      ['Stop loss',   fP(slL), fP(slS), 'r','r'],
      ['Entry',       fP(e),   fP(e),   'ac'],
      ['Breakeven',   fP(beL), fP(beS)],
      ['Liquidation', liqL>0?fP(liqL):'none', fP(liqS), 'a','a'],
      ['Stop / TP move', pc(t.stop_pct), pc(t.tp_pct), 'r','g'],
    ])
  + sec('Prop rule sizing', [
      ['Eval equity', fP(t.account), 'nominal '+fP(t.account_nominal), 'ac', 'dim'],
      ['Risk / trade', pc(t.actual_risk_pct), fP(t.risk_usd), 'r','r'],
      ['Notional', fP(t.notional), t.size_btc.toFixed(4)+' ₿'],
      ['Margin', fP(t.margin_usd), pc(t.margin_pct)+' of acct'],
      ['Leverage', lev.toFixed(2)+'×', 'min '+t.min_leverage+'× · cap '+t.max_leverage+'×', 'ac', 'dim'],
      ['R:R (net)', t.rr.toFixed(2)+'×', ''],
    ])
  + sec('Outcome', [
      ['Win',  '+'+fP(t.win_usd),  fP(t.account+t.win_usd),  'g','g'],
      ['Loss', '−'+fP(t.loss_usd), fP(t.account-t.loss_usd), 'r','r'],
      ['Win rate (hist)', pc(t.win_rate_pct), ''],
      ['Strategy', t.strategy, t.eval, 'dim','dim'],
    ])
  + (o ? overrideSec(t, o) : '');
  $('out').innerHTML='<div class="grid">'+out+'</div>';
  // log the ticket you'd actually place — the override when there is one
  const k = o || t;
  // levels() already resolves the override's own stop/target, so `k` carries the
  // plan actually being placed rather than the strategy default it replaced
  const kl = levels(k);
  LAST={book:'prop',direction:dir,entry:k.entry,size:k.size_btc,leverage:k.leverage,
        tp:(dir==='long'?kl.tpL:kl.tpS), sl:(dir==='long'?kl.slL:kl.slS)};
  $('logbar').style.display='flex';
  $('logmsg').textContent = o ? 'logs the OVERRIDE ticket ('+pc(o.stop_pct)+' stop)' : '';
}

async function logTrade(){
  if(!LAST||!LAST.entry){ return; }
  $('logbtn').disabled=true; $('logmsg').textContent='logging…';
  try{
    const r=await fetch('/api/trades',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({symbol:'BTC/USD',direction:LAST.direction,entry:LAST.entry,
        size:Number(LAST.size.toFixed(6)),leverage:LAST.leverage,book:LAST.book,
        // the plan as it stood at entry, overrides included — this is what the
        // review later compares reality against
        tp:LAST.tp!=null?Number(LAST.tp.toFixed(2)):null,
        sl:LAST.sl!=null?Number(LAST.sl.toFixed(2)):null})});
    if(!r.ok){ throw new Error((await r.json()).detail||'log failed'); }
    const t=await r.json();
    $('logmsg').innerHTML='✓ logged open '+LAST.direction+' #'+t.id+' · <a href="/hedge-journal?trade='+t.id+'" style="color:var(--accent)">journal</a>';
  }catch(e){ $('logmsg').textContent='✗ '+(e.message||e); }
  $('logbtn').disabled=false;
}

// calculator — type 60000*1.02 → Enter/blur → evaluates, then re-sizes
['p-entry','p-bal','p-btc','o-std'].forEach(id=>{
  const inp=$(id);
  if(!inp) return;
  function tryCalc(){ const v=inp.value.trim(); if(!v||!/[+*\/]/.test(v))return;
    try{ const r=Function('"use strict";return('+v.replace(/[^0-9+\-*/.() \t]/g,'')+')')();
      if(isFinite(r)){ inp.value=parseFloat(r.toFixed(8)); calc(); } }catch(e){} }
  inp.addEventListener('input', ()=>{ clearTimeout(deb); deb=setTimeout(calc, 250); });
  inp.addEventListener('blur', tryCalc);
  inp.addEventListener('keydown', e=>{ if(e.key==='Enter'){ tryCalc(); e.preventDefault(); } });
});

// arrive via /prop-position → the Prop tab is already selected
if(START_BOOK==='prop') setBook('prop');


// The trade, at the size in the ticket — not at the size LENS suggested. Typing
// 0.001 has to move these numbers, or the form and the readout are two screens
// that happen to share a page. Prices don't depend on size; the € figures do,
// so only those are scaled, and the page says so when they are.
// NB: `LAST` is already taken — it's the trade-log payload. This is TRADE.
let TRADE = null;

function tradeBlock(){
  if(!TRADE) return '';
  const q = xqty() || TRADE.full;
  const k = TRADE.full ? q / TRADE.full : 1;
  const long = dir === 'long';
  const tp  = long ? TRADE.tpL  : TRADE.tpS;
  const sl  = long ? TRADE.slL  : TRADE.slS;
  const liq = long ? TRADE.liqL : TRADE.liqS;
  const b   = TRADE.bal;
  const win = TRADE.gainE * k, loss = TRADE.lossE * k;

  // Reachability, as a tick or a cross. The earlier version printed a distance
  // in standard deviations, which is the right maths and the wrong words — it
  // isn't how he reads a ticket. The question a level actually poses is binary:
  // can price get there in a normal session or not.
  // Is this level inside a normal 8-hour move? A tick or a cross beside the
  // price, because that's the only question being asked of it.
  const reach = px => TRADE.sigma ? Math.abs(px - TRADE.e) <= TRADE.sigma : null;
  const mark = px => { const ok = reach(px); return ok==null ? ''
    : ok ? '<i class="ok" title="within a normal 8-hour move">✓</i>'
         : '<i class="no" title="beyond a normal 8-hour move">✗</i>'; };

  // Risk against the optimal bet: under it is green, up to 1.5x amber, past
  // that red. The percentages are of the balance, at the size in the ticket.
  const riskPctNow = b ? loss / b * 100 : 0;
  const kelly = TRADE.kellyPct || 0;
  const rk = !kelly ? '' : riskPctNow <= kelly ? 'good'
           : riskPctNow <= kelly * 1.5 ? 'warn' : 'bad';

  const row = (cls, label, price, mkt, acct, money, after, tag) =>
    `<div class="tl ${cls}"><span class="k">${label}</span>`
    + `<span class="p">${fP(price)}${tag||''}</span>`
    + `<span class="mk">${mkt||''}</span>`
    + `<span class="ac">${acct||''}</span>`
    + `<span class="m">${money||''}</span>`
    + `<span class="a">${after||''}</span></div>`;

  const off = TRADE.full && Math.abs(q - TRADE.full) / TRADE.full > 0.005;

  return '<div class="tw">'
    + `<div class="ct">The trade · ${q.toFixed(6)} ₿ ${long?'long':'short'}`
      + `<span class="rr">${(TRADE.rr||0).toFixed(2)}R net</span></div>`
    + `<div class="tl th"><span class="k"></span><span class="p">price · 8h</span>`
      + `<span class="mk">market</span><span class="ac">account</span>`
      + `<span class="m">€</span><span class="a">balance</span></div>`
    + row('tp','Take profit', tp, '+'+pc(TRADE.winMkt), '+'+pc(TRADE.winAcct*k),
          '+'+fE(win), fE(b+win), mark(tp))
    + row('en','Entry', TRADE.e, '', '', '', fE(b), '')
    + row('sl','Stop loss', sl, '−'+pc(TRADE.lossMkt), '−'+pc(TRADE.lossAcct*k),
          '−'+fE(loss), fE(b-loss), mark(sl))
    + row('liq','Liquidation', liq, '', '', '', TRADE.lev.toFixed(1)+'×', mark(liq))
    + `<div class="risk"><span class="${rk}">Risking <b>${fE(loss)}</b> of ${fE(b)}`
      + ` · <b>${riskPctNow.toFixed(2)}%</b></span>`
      + `<span class="rec">optimal ${kelly.toFixed(2)}% · plan ${(TRADE.riskPct||0).toFixed(2)}%`
      + ` · typical win ${(TRADE.typicalWin||0).toFixed(1)}%</span></div>`
    + (off ? `<div class="scaled">Sized at ${q.toFixed(6)} ₿ — ${(k*100).toFixed(0)}% of the `
             + `${TRADE.full.toFixed(6)} ₿ recommendation. Prices and market % are unchanged; `
             + `the € and account % scale with size.</div>` : '')
    + `<div class="legend"><i class="ok">✓</i> reachable inside a normal 8-hour move `
      + `(±${fP(TRADE.sigma)} from entry) · <i class="no">✗</i> beyond it.</div>`
    + '</div>';
}

// Repaint just the readout when the quantity changes — no refetch, no flicker.
function repaintTrade(){
  const host = document.querySelector('.tw');
  if(host) host.outerHTML = tradeBlock();
}

// ── Order panel ─────────────────────────────────────────────────────────────
// Sends the ticket THIS page computed — including the take profit and stop loss
// it already worked out, which is the part the exchange's own form makes you
// retype. Nothing here decides anything: every gate is evaluated server-side by
// /api/execute/check and re-evaluated on send, so a stale page cannot talk the
// server into an order.
let XFULL=0, XPCT=100, XARM=null, XOPEN=null, XMARK=0, XLIQ=null, XLEVELS=null, XOT='mkt';

const xn = id => { const v=parseFloat($(id).value); return isFinite(v)?v:null; };
function xqty(){ return xn('x-qty') || 0; }
// One price field. Entry and "limit price" were the same number in two inputs;
// in market mode it's the reference price the ticket is sized against, in limit
// mode it's the price actually sent.
function ref(){ return xn('p-entry') || XMARK || 0; }

function setOT(t){
  XOT=t;
  document.querySelectorAll('#x-otype .xp').forEach(b=>
    b.classList.toggle('on', b.textContent.toLowerCase().startsWith(t==='mkt'?'market':'limit')));
  $('x-pricelab').textContent = t==='lmt' ? 'Limit price USD' : 'Entry price USD';
  $('x-tif-wrap').style.display = t==='lmt' ? '' : 'none';
  paintExec();
}

// One click takes the whole recommendation — size and leverage together, since
// taking the size at a different leverage is a different trade.
function useRecommended(){
  if(TRADE) $('x-lev').value = TRADE.lev.toFixed(1);
  setPct(100);
}

function setPct(v, fromSlider){
  XPCT=Math.max(1,Math.min(100,Math.round(+v)));
  if(!fromSlider) $('x-pct').value=XPCT;
  $('x-pctv').textContent=XPCT+'%';
  document.querySelectorAll('#x-pctseg .xp').forEach(b=>b.classList.toggle('on', b.textContent===XPCT+'%'));
  $('x-qty').value = (XFULL*XPCT/100).toFixed(6);
  syncUsd(); disarm(); paintExec(); repaintTrade();
}

function syncUsd(){ const r=ref(); $('x-usd').value = r ? (xqty()*r).toFixed(2) : ''; }
function qtyEdited(){ syncUsd(); disarm(); paintExec(); repaintTrade(); }
function usdEdited(){
  const r=ref(), u=xn('x-usd');
  if(r && u) $('x-qty').value=(u/r).toFixed(6);
  disarm(); paintExec(); repaintTrade();
}

function toggleTPSL(){
  const on=$('x-tpsl').checked;
  $('x-tpslbox').style.display = on ? '' : 'none';
  if(on) fillLevels();
  disarm(); paintExec();
}

// The whole point: TP/SL come from the levels this page computed for the
// direction currently selected.
function fillLevels(){
  if(!XLEVELS) return;
  const L = dir==='long' ? XLEVELS.long : XLEVELS.short;
  $('x-tp').value = L.tp.toFixed(1);
  $('x-sl').value = L.sl.toFixed(1);
}

function ticket(){
  const useB = $('x-tpsl').checked;
  // "Good till cancelled" and "Immediate or cancel" ARE order types on this
  // exchange, not a separate flag — so time in force selects the type.
  const ot = XOT==='lmt' ? ($('x-tif').value || 'lmt') : XOT;
  return {direction:dir, size_btc:xqty(), order_type:ot,
          limit_price: XOT==='lmt' ? xn('p-entry') : null,
          take_profit: useB ? xn('x-tp') : null,
          stop_loss:   useB ? xn('x-sl') : null,
          mark: XMARK || null,
          trigger_signal: $('x-trig').value, leverage: xn('x-lev') || 10,
          override_reason: ($('x-ovr-why').value || '').trim() || null};
}

async function post(url, body){
  const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
                          body:JSON.stringify(body)});
  return r.json();
}

async function paintExec(){
  if(!XFULL) return;
  const t=ticket();
  const lev=t.leverage, r=ref();
  $('x-mark').textContent = XMARK ? 'mark '+XMARK.toFixed(1) : 'mark —';
  $('d-inc').textContent  = (dir==='long'?'Long ':'Short ')+xqty().toFixed(6)+' BTC';
  $('d-liq').textContent  = XLIQ ? '$'+XLIQ.toFixed(0) : '—';
  $('d-fee').textContent  = r ? '$'+(xqty()*r*0.0005).toFixed(4) : '—';
  try{
    const c=await post('/api/execute/check', t);
    $('x-env').textContent = c.sandbox ? 'DEMO' : 'LIVE';
    $('x-env').className   = 'xenv '+(c.sandbox?'demo':'live');
    $('s-env').textContent = c.sandbox ? 'DEMO' : 'LIVE';
    $('s-env').className   = 'xenv '+(c.sandbox?'demo':'live');
    $('d-margin').textContent = c.required_margin_usd!=null ? '$'+c.required_margin_usd.toFixed(2) : '—';
    $('d-cap').textContent    = (+c.size_cap_btc).toFixed(6)+' ₿';
    // A setup refusal opens the box instead of ending the conversation.
    const setupBlocked = c.setup_note && (!c.ok
      ? c.reasons.some(r=>r.startsWith('no_setup')||r.startsWith('setup_veto'))
      : c.overriding);
    $('x-ovr').style.display = setupBlocked ? 'block' : 'none';
    if(setupBlocked) loadMarketRead(); else MREAD_DIR = null;
    if(setupBlocked) $('x-ovr-n').textContent = c.overriding
      ? 'Recorded with the trade — ' + c.setup_note
      : 'The scanner: ' + c.setup_note + '. Say what you see and it goes through, logged.';

    if(c.ok){
      const legs=c.orders.map(o=>o.order_tag).join(' + ');
      $('x-gates').innerHTML = c.overriding
        ? '<span class="ovrf">⚑</span> going against the scanner — this will be recorded'
        : '<span class="yes">✓</span> gates pass — sending: <b>'+legs+'</b>';
      $('x-go').disabled=false;
    } else {
      $('x-gates').innerHTML=c.reasons.map(x=>'<span class="no">✗ '+x+'</span>').join('<br>');
      $('x-go').disabled=true;
    }
  }catch(e){ $('x-gates').textContent='gate check failed: '+e; $('x-go').disabled=true; }
}

// A modal, deliberately. Product guidance says exhaust inline alternatives
// first, and the earlier two-step arm was that alternative — but an order is
// irreversible and spends real money, which is exactly the case a confirm
// dialog exists for. Native <dialog> so it can't be clipped by an ancestor's
// overflow, and so Esc and the backdrop work without being reimplemented.
let PENDING = null;

function disarm(){
  const g=$('x-go');
  g.textContent=(dir==='short'?'▼ ':'▲ ')+'Execute '+dir;
  g.classList.toggle('short', dir==='short');
}

function fillDetails(c, t){
  const lim = t.order_type==='lmt' ? ' @ '+fP(t.limit_price) : ' @ market';
  $('d-inc').textContent    = (t.direction==='long'?'Long ':'Short ')
                              + Number(t.size_btc).toFixed(6)+' BTC'+lim;
  $('d-tp').textContent     = t.take_profit ? fP(t.take_profit) : 'none';
  $('d-sl').textContent     = t.stop_loss   ? fP(t.stop_loss)   : 'none';
  $('d-margin').textContent = c.required_margin_usd!=null ? '$'+c.required_margin_usd.toFixed(2) : '—';
  $('d-liq').textContent    = XLIQ ? fP(XLIQ) : '—';
  $('d-fee').textContent    = ref() ? '$'+(t.size_btc*ref()*0.0005).toFixed(4) : '—';
  $('d-cap').textContent    = (+c.size_cap_btc).toFixed(6)+' ₿';
  $('dlg-env').textContent  = c.sandbox ? 'DEMO' : 'LIVE';
  $('dlg-env').className    = 'xenv '+(c.sandbox?'demo':'live');
  $('dlg-warn').textContent = c.sandbox
    ? 'Demo exchange — this does not touch the live account.'
    : 'This sends a real order on the live account.';
  $('dlg-warn').className   = 'dwarn '+(c.sandbox?'':'live');
}

async function askExec(){
  const t = ticket();
  const c = await post('/api/execute/check', t);
  if(!c.ok){ $('x-msg').textContent='✗ '+c.reasons.join(' · '); return; }
  PENDING = {kind:'exec', t};
  $('dlg-t').textContent   = 'Confirm order';
  $('dlg-lead').textContent= (t.direction==='long'?'LONG ':'SHORT ')
                             + Number(t.size_btc).toFixed(6)+' BTC';
  $('dlg-lead').className  = 'dlead '+t.direction;
  $('dlg-go').textContent  = 'Send '+t.direction;
  $('dlg-go').className    = 'xgo'+(t.direction==='short'?' short':'');
  fillDetails(c, t);
  $('x-dlg').showModal();
}

async function askClose(){
  if(!XOPEN){ $('x-msg').textContent='no open position'; return; }
  const t = {direction:XOPEN.direction, size_btc:XOPEN.size, order_type:'mkt',
             mark:XMARK||null, leverage:xn('x-lev')||10};
  const c = await post('/api/execute/check',
              {direction: XOPEN.direction==='long'?'short':'long',
               size_btc:XOPEN.size, order_type:'mkt', mark:XMARK||null, reduce_only:true});
  PENDING = {kind:'close', t};
  $('dlg-t').textContent   = 'Close position';
  $('dlg-lead').textContent= 'Close '+XOPEN.size+' BTC '+XOPEN.direction;
  $('dlg-lead').className  = 'dlead';
  $('dlg-go').textContent  = 'Close position';
  $('dlg-go').className    = 'xgo short';
  fillDetails(c, {direction: XOPEN.direction==='long'?'short':'long',
                  size_btc: XOPEN.size, order_type:'mkt'});
  $('d-inc').textContent   = 'Reduce-only market order, '+XOPEN.size+' BTC';
  $('d-tp').textContent='—'; $('d-sl').textContent='—';
  $('x-dlg').showModal();
}

function closeDlg(){ PENDING=null; $('x-dlg').close(); }

async function confirmDlg(){
  if(!PENDING) return closeDlg();
  const kind = PENDING.kind, t = PENDING.t;
  $('dlg-go').disabled = true;
  $('dlg-go').textContent = 'sending…';
  const r = kind==='exec'
    ? await post('/api/execute', Object.assign({}, t, {confirm:true}))
    : await post('/api/execute/close',
        {direction:t.direction, size_btc:t.size_btc, confirm:true, mark:XMARK||null});
  $('dlg-go').disabled = false;
  closeDlg();
  $('x-msg').textContent = r.sent
    ? (kind==='exec' ? '✓ sent — '+t.direction+' '+Number(t.size_btc).toFixed(6)+' ₿'
                     : '✓ close sent')
    : '✗ '+(r.blocked||'blocked')+(r.error?' — '+r.error:'');
  loadLive();
}

async function cancelAll(){
  $('x-msg').textContent='cancelling resting orders…';
  const r=await post('/api/execute/cancel-all',{});
  $('x-msg').textContent = r.ok ? '✓ resting orders cancelled' : '✗ '+(r.error||'failed');
  loadLive();
}

const fU = v => v==null ? '—' : '$'+(+v).toLocaleString(undefined,{maximumFractionDigits:0});

// Resting orders and the prices the triggers fire on. This is the exchange's
// truth; the ticket above is a proposal. Keeping them visibly separate is the
// whole point — the planned take-profit was being read as the live one.
// The argument behind the refusal. A verdict with a hit rate attached is not a
// case; these are the readings he actually trades off, each with a stance, so
// going against the scanner is a decision rather than a shrug.
let MREAD_DIR = null;
async function loadMarketRead(){
  if(MREAD_DIR === dir) return;             // only refetch when the side changes
  MREAD_DIR = dir;
  try{
    const d = await fetch('/api/market/read?direction='+dir).then(r=>r.json());
    if(!d.ok){ $('x-mread').innerHTML=''; return; }
    const tally = `<span class="tally">${d.agree} agree · <b>${d.against} against</b> your ${dir}</span>`;
    $('x-mread').innerHTML =
      `<div class="mrh"><span>What the market reads — 1h</span>${tally}</div>`
      + d.readings.map(r=>`<div class="mr ${r.stance}">`
          + `<span class="n">${r.name}</span>`
          + `<span class="t">${r.note}</span>`
          + `<span class="v">${r.value}</span></div>`).join('');
  }catch(e){ $('x-mread').innerHTML=''; }
}

async function loadOrders(){
  try{
    const d = await fetch('/api/orders/live').then(r=>r.json());
    const p = d.prices || {};
    if(p.mark)  { $('s-mark').textContent  = Math.round(p.mark).toLocaleString('en'); XMARK = p.mark; }
    if(p.index) { $('s-index').textContent = Math.round(p.index).toLocaleString('en'); }
    if(p.last)  { $('s-last').textContent  = Math.round(p.last).toLocaleString('en'); }

    const mine = (d.orders||[]).filter(o=>o.account==='personal');
    const tp = mine.find(o=>o.role==='take_profit');
    const sl = mine.find(o=>o.role==='stop_loss');
    $('s-tp').textContent = tp ? fP(tp.trigger) : '—';
    $('s-sl').textContent = sl ? fP(sl.trigger) : '—';

    $('ord-n').textContent = mine.length ? mine.length+' resting' : 'none';
    $('ord-list').innerHTML = mine.length ? mine.map(o=>{
      const cls = o.role==='take_profit' ? 'tp' : o.role==='stop_loss' ? 'sl' : 'entry';
      const name = o.role==='take_profit' ? 'take profit'
                 : o.role==='stop_loss'   ? 'stop loss' : (o.order_type+' '+o.side);
      const px = o.trigger || o.limit;
      return `<div class="ord ${cls}"><span class="role">${name}</span>`
        + `<span class="meta">${o.size||''} ${o.reduce_only?'· reduce-only':''}`
        + ` · on ${o.trigger_on||'—'}</span>`
        + `<span class="px">${px?fP(px):'—'}</span>`
        + `<button type="button" onclick="cancelOne('${o.order_id}')">cancel</button></div>`;
    }).join('') : '<div class="ordnone">Nothing resting on the exchange.</div>';
  }catch(e){}
}

async function cancelOne(id){
  $('x-msg').textContent='cancelling…';
  const r = await fetch('/api/orders/cancel?order_id='+encodeURIComponent(id),
                        {method:'POST'}).then(r=>r.json());
  $('x-msg').textContent = r.ok ? '✓ order cancelled' : '✗ '+(r.error||'failed');
  loadOrders(); loadLive();
}

async function loadLive(){
  try{
    const a=await fetch('/api/account/live').then(r=>r.json());
    $('d-avail').textContent = a.available_margin!=null ? '€'+a.available_margin.toFixed(2) : '—';
    $('s-bal').textContent   = a.total_eur!=null ? '€'+a.total_eur.toFixed(2) : '—';
    $('s-avail').textContent = a.available_margin!=null ? '€'+a.available_margin.toFixed(2) : '—';
    const u=a.unrealized_pnl;
    if(u!=null){ $('s-upnl').textContent=(u>=0?'+':'')+'€'+u.toFixed(2);
                 $('s-upnl').className='sv '+(u>=0?'g':'r'); }
  }catch(e){}
  try{
    const p=await fetch('/api/positions/live').then(r=>r.json());
    const mine=(p.positions||[]).filter(x=>x.account==='personal');
    XOPEN = mine.length ? mine[0] : null;
    $('x-close').disabled = !XOPEN;
    $('s-close').disabled = !XOPEN;
    if(mine.length){
      // The strip is the only place the position is shown now — the separate
      // panel underneath was the same numbers a second time.
      const o=mine[0], up=o.upnl_eur||0;
      $('s-open').textContent  = o.direction+' '+o.size+' ₿ · '+(o.leverage||'')+'×';
      $('s-open').className    = 'sv '+(o.direction==='long'?'g':'r');
      $('s-upnl').textContent  = (up>=0?'+':'')+'€'+up.toFixed(2)
                                 +' · '+(o.roe_pct||0).toFixed(1)+'% RoE';
      $('s-upnl').className    = 'sv '+(up>=0?'g':'r');
      $('s-entry').textContent = fU(o.entry)+' · '+fU(o.liquidation);
      $('s-mark').textContent  = o.mark ? Math.round(o.mark).toLocaleString('en') : '—';
    } else {
      $('s-open').textContent='flat'; $('s-open').className='sv';
      $('s-entry').textContent='—';
    }
    loadOrders();
  }catch(e){}
}

(async ()=>{ const c=await ensureCfg();
  HEDGE_BAL = c.start_balance!=null ? c.start_balance : null;
  if(c.start_balance!=null) $('p-bal').placeholder=c.start_balance;
  if(c.btc_price_eur!=null) $('p-btc').placeholder=c.btc_price_eur;
  // live balance + BTC price + auto daily σ (best-effort)
  try{ const a=await fetch('/api/account/live').then(r=>r.json());
    if(a.total_eur){ HEDGE_BAL=a.total_eur.toFixed(2); if(book==='hedge') $('p-bal').value=HEDGE_BAL; }
    const v=await fetch('/api/volatility').then(r=>r.json());
    if(v.btc_usd){ $('p-entry').placeholder=v.btc_usd.toFixed(0); if(!$('p-entry').value){ $('p-entry').value=v.btc_usd.toFixed(0); calc(); } }
    if(v.btc_usd && a.eur_usd) $('p-btc').value=(v.btc_usd/a.eur_usd).toFixed(2);
    if(v.daily_sigma){ $('o-std').placeholder=v.daily_sigma; if(!$('o-std').value) $('o-std').value=v.daily_sigma; }
  }catch(e){}
})();
"""
    from .prop_views import prop_config
    from .prop_eval import EVALS
    cfg = prop_config()
    prop_def = {"account": cfg["account"], "risk": round(cfg["risk"] / 100, 4),
                "leverage": EVALS[cfg["eval_name"]]["max_leverage"]}
    script = f"const PROP={json.dumps(prop_def)};\nconst START_BOOK=\"{book}\";\n" + script
    # /prop-position keeps the PROP nav + preselects the Prop tab (see theme.NAV_PROP).
    # On the prop page there's no hedge sizing — lock the book and hide the
    # hedge-only inputs (BTC € price, win-rate override). Balance (eval $) and the
    # risk/R:R/leverage-cap overrides stay: per-trade what-ifs against the plan.
    path = "/prop-position" if book == "prop" else "/hedge-position"
    head = _CSS + _XCSS + ("<style>#book-preset-row,#f-btc,#f-wr{display:none!important}</style>"
                   if book == "prop" else "")
    return shell(path, "Position", body, script=script, head_extra=head, meta="size the trade")
