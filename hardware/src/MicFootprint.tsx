import { type ChipProps } from "tscircuit"
export const MicFootprint = (props: ChipProps) => (
  <chip
    footprint={<footprint>
        <hole pcbX="0mm" pcbY="-0.77mm" diameter="0.5mm" />
<smtpad portHints={["1"]} pcbX="-0.8375mm" pcbY="1.304mm" layer="top" width="0.725mm" height="0.522mm" shape="rect" />
<smtpad portHints={["2"]} pcbX="-0.8375mm" pcbY="0.482mm" layer="top" width="0.725mm" height="0.522mm" shape="rect" />
<smtpad portHints={["3"]} pcbX="0mm" pcbY="-0.7700000000000001mm" layer="top" radius="0.8125mm" shape="circle" />
<smtpad portHints={["4"]} pcbX="0.8375mm" pcbY="0.482mm" layer="top" width="0.725mm" height="0.522mm" shape="rect" />
<smtpad portHints={["5"]} pcbX="0.8375mm" pcbY="1.304mm" layer="top" width="0.725mm" height="0.522mm" shape="rect" />
<silkscreenpath route={[{"x":-1.44,"y":-1.86},{"x":-1.44,"y":1.56}]} />
<silkscreenpath route={[{"x":-1.14,"y":1.86},{"x":1.44,"y":1.86}]} />
<silkscreenpath route={[{"x":1.44,"y":1.86},{"x":1.44,"y":-1.86}]} />
<silkscreenpath route={[{"x":1.44,"y":-1.86},{"x":-1.44,"y":-1.86}]} />
<silkscreenpath route={[{"x":-1.44,"y":1.86},{"x":-1.72,"y":1.86},{"x":-1.44,"y":2.14},{"x":-1.44,"y":1.86}]} />
<fabricationnotepath route={[{"x":-1.325,"y":-1.75},{"x":-1.325,"y":0.86}]} strokeWidth={0.1} />
<fabricationnotepath route={[{"x":-0.435,"y":1.75},{"x":-1.325,"y":0.86}]} strokeWidth={0.1} />
<fabricationnotepath route={[{"x":1.325,"y":1.75},{"x":-0.435,"y":1.75}]} strokeWidth={0.1} />
<fabricationnotepath route={[{"x":1.325,"y":1.75},{"x":1.325,"y":-1.75}]} strokeWidth={0.1} />
<fabricationnotepath route={[{"x":1.325,"y":-1.75},{"x":-1.325,"y":-1.75}]} strokeWidth={0.1} />
<fabricationnotetext pcbX={0} pcbY={-3} anchorAlignment="center" text="Knowles_LGA-5_3.5x2.65mm" font="tscircuit2024" fontSize={1} />
<fabricationnotetext pcbX={0} pcbY={0.1} anchorAlignment="center" text="REF**" font="tscircuit2024" fontSize={0.7} />
<silkscreentext pcbX={0} pcbY={2.8} anchorAlignment="center" fontSize={1} font="tscircuit2024" layer="top" text="REF**" />
<courtyardoutline outline={[{"x":-1.58,"y":2},{"x":1.58,"y":2}]} layer="top" />
<courtyardoutline outline={[{"x":-1.58,"y":-2},{"x":-1.58,"y":2}]} layer="top" />
<courtyardoutline outline={[{"x":1.58,"y":2},{"x":1.58,"y":-2}]} layer="top" />
<courtyardoutline outline={[{"x":1.58,"y":-2},{"x":-1.58,"y":-2}]} layer="top" />
      </footprint>}
    {...props}
  />
)