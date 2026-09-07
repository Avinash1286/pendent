# Toolchain and reproduction

This project was authored on Windows with PowerShell. Source files and lockfiles are provided; installed dependencies, authentication files, temporary caches and application binaries are intentionally not checked into Git.

| Workstream | Tools |
| --- | --- |
| Electronics | tscircuit, TypeScript/TSX, Bun, KiCad 10, Java/Freerouting for independent routing |
| Industrial design | Blender 5.2.1 LTS, bundled Python, Cycles, glTF and STL exporters |
| Website | Node.js, npm, React 19, Vite 8, TypeScript, Three.js, Base UI, Vercel CLI |
| Launch film | Hyperframes 0.8.31, local Chrome renderer, GSAP, FFmpeg, original locally synthesized soundtrack |

Use each workstream's README for its exact commands. `npm ci` uses the committed package lockfile. Blender scripts should run in their own background Blender process because the generator replaces that process's scene.

## Documentation used

- [tscircuit documentation](https://docs.tscircuit.com/) — installation, JSX elements, PCB/footprint definitions and export tooling. Component datasheets and hardware-specific sources are listed with the hardware design.
- [Blender manual](https://docs.blender.org/manual/en/latest/) and the installed Blender Python API — model generation, rendering and geometry export.
- [Three.js documentation](https://threejs.org/docs/) — GLTFLoader, OrbitControls, lighting and rendering.
- [Hyperframes upstream](https://github.com/heygen-com/hyperframes) — the locally installed router/workflow/core/animation/creative/CLI skills, seekable composition format, lint/check and rendering.
- [Vercel deployment documentation](https://vercel.com/docs/cli/deploy) and [Git deployment configuration](https://vercel.com/docs/project-configuration/git-configuration) — direct CLI publication and disabled automatic Git deployments during project checkpoints.

## Dependency audit boundary

The website's production dependency audit reported zero known vulnerabilities at the delivery check; its machine-readable report is in `website/audit-production.json`. The development toolchain's Vercel CLI transitive dependency tree still reports upstream advisories. The public website is a static build and does not deploy that CLI tree or a Node server. A non-breaking audit remediation and Vite update were applied; forced downgrade/major replacement of the deployment CLI was not applied. Hardware records its own dependency audit.

No API keys, provider tokens, local environment files or session credentials are included in the repository. No GitHub Actions workflows are configured. Publication is performed with Vercel directly.
