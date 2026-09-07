import fs from 'node:fs';
// These are the original authored geometry targets, carried into the independent
// KiCad project. They are not a factory capability approval.
const project={
 board:{design_settings:{defaults:{},diff_pair_dimensions:[],drc_exclusions:[],rules:{
  min_clearance:0.12,min_track_width:0.12,min_via_diameter:0.45,
  min_through_hole_diameter:0.2,min_hole_to_hole:0.25,copper_edge_clearance:0.3,
  min_silk_line_width:0.1,min_text_height:0.7
 },track_widths:[0,0.15,0.3],via_dimensions:[{diameter:0.45,drill:0.2}]}},
 boards:[],libraries:{pinned_footprint_libs:[],pinned_symbol_libs:[]},
 meta:{filename:'aura-placement.kicad_pro',version:1},
 net_settings:{classes:[{name:'Default',clearance:0.12,track_width:0.15,via_diameter:0.45,via_drill:0.2,
  diff_pair_width:0.15,diff_pair_gap:0.15,diff_pair_via_gap:0.2,microvia_diameter:0.3,microvia_drill:0.1}],
  meta:{version:4},net_colors:null,netclass_assignments:null,netclass_patterns:[]},
 pcbnew:{page_layout_descr_file:''},sheets:[],text_variables:{}
};
fs.writeFileSync('output/aura-placement.kicad_pro',JSON.stringify(project,null,2));
console.log('KiCad draft rules written: 0.12mm clearance / 0.15mm default trace / 0.45mm via / 0.20mm drill.');
