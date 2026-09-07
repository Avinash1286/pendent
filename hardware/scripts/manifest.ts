import fs from 'node:fs';
import {parts,boardSpec} from '../src/design';
fs.writeFileSync('output/design-manifest.json',JSON.stringify({parts,boardSpec},null,2));
