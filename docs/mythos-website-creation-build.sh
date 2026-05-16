#!/usr/bin/env bash

# -----------------------------------------------
# mythos — Autonomous Premium Web Build CLI
# -----------------------------------------------
# Claude Code = architect, designer, reviewer (probabilistic)
# Codex       = deterministic code executor, test writer, patcher
# -----------------------------------------------

# 0. One-time VPS bootstrap
mythos init \
  --workdir ~/projects \
  --claude-key $ANTHROPIC_API_KEY \
  --codex-key  $OPENAI_API_KEY \
  --sandbox firecracker          # or gvisor
  --mcp firecrawl,nano-banana-2,relume,stitch,spline

# 1. Create a new project skeleton (folders from claude.md brain)
mythos new <project-name> \
  --stack next,tailwind,shadcn,supabase,stripe,resend \
  --hosting netlify \
  --assets cloudflare-r2 \
  --workflows modal,trigger.dev

# 2. Plan Mode — Claude Code drafts scope, wireframes via Relume, asks clarifying Qs
mythos plan \
  --brief ./brief.md \
  --inspiration awwwards,godly,dribbble \
  --quality-bar 7          # the 7-Level Design Quality Bar
  --emit plan.md

# 3. Execute — autonomous build (bypass-permissions once plan is approved)
mythos build \
  --plan plan.md \
  --agent architect        # threat-models first
  --agent implementation   # Codex writes secure-by-default code
  --skills frontend-design,uiux-pro-max,site-teardown,awesome-design

# 4. Visual QA — Puppeteer screenshot loop (min. 2 passes)
mythos review \
  --passes 2 \
  --screenshots ./temporary_screenshots \
  --fix layout,padding,typography,contrast

# 5. Red/Blue adversarial hardening (Mythos Defense)
mythos harden \
  --zones A:target,B:control,denied:public \
  --classes authn,injection,access,crypto,toctou,api,supply-chain,config \
  --red-team codex         # must produce working PoC per finding
  --blue-team claude       # patches root cause, writes regression test
  --max-escalations 3      # escalate to human after 3 failed patches

# 6. Supply chain + SBOM
mythos audit --sbom cyclonedx --deps npm,pnpm,pip

# 7. Sandbox run (pre-deploy)
mythos sandbox up --port 3000 --isolate firecracker
mythos sandbox smoke --e2e playwright

# 8. Deploy decision matrix (presents options + cost table)
mythos deploy \
  --compare netlify,vercel,github-pages,hostinger-vps,aws,modal,abacus \
  --show cost,features,latency,ai-fit \
  --target netlify         # selected after review

# 9. Ongoing autonomy
mythos watch    # Trigger.dev/Modal scheduled re-scans + self-heal
mythos report   # weekly security + perf report to ./reports/