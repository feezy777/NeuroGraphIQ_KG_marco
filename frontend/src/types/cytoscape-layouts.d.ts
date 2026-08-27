/**
 * cytoscape 布局插件类型声明（社区包无类型）：
 * - cytoscape-fcose  : fcose 力导向布局（默认布局引擎）
 * - cytoscape-dagre  : 备选分层布局（大规模模式）
 */
declare module 'cytoscape-fcose' {
  import type { LayoutOptions } from 'cytoscape'
  const fcose: cytoscape.Ext
  export default fcose
}

declare module 'cytoscape-dagre' {
  import type { LayoutOptions } from 'cytoscape'
  const dagre: cytoscape.Ext
  export default dagre
}
