'use client';

import { useEffect, useRef, useCallback } from 'react';
import * as d3 from 'd3';
import { ROLE_COLORS, SEVERITY_COLORS, type PostRole, type Severity } from '@/lib/constants';
import type { CannibalizationPair, PostHealth } from '@/lib/types';

interface NetworkNode extends d3.SimulationNodeDatum {
  id: string;
  title: string;
  url: string;
  role: PostRole;
  traffic: number;
  clusterId: string | null;
}

interface NetworkLink extends d3.SimulationLinkDatum<NetworkNode> {
  pairId: string;
  overlapScore: number;
  severity: Severity;
}

interface NetworkGraphProps {
  posts: PostHealth[];
  pairs: CannibalizationPair[];
  onSelectNode: (postId: string | null) => void;
  onSelectEdge: (pairId: string | null) => void;
  severityFilter: Severity[];
  clusterFilter: string | null;
}

export function NetworkGraph({
  posts,
  pairs,
  onSelectNode,
  onSelectEdge,
  severityFilter,
  clusterFilter,
}: NetworkGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const buildGraph = useCallback(() => {
    if (!svgRef.current || !containerRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = containerRef.current.clientWidth;
    const height = containerRef.current.clientHeight;

    svg.attr('width', width).attr('height', height);

    // Filter pairs by severity
    const filteredPairs = pairs.filter(
      (p) => severityFilter.includes(p.severity)
    );

    // Filter by cluster
    const filteredByCluster = clusterFilter
      ? filteredPairs.filter((p) => p.cluster_id === clusterFilter)
      : filteredPairs;

    // Build node set from filtered pairs
    const nodeIds = new Set<string>();
    filteredByCluster.forEach((p) => {
      nodeIds.add(p.post_a_id);
      nodeIds.add(p.post_b_id);
    });

    const nodes: NetworkNode[] = posts
      .filter((p) => nodeIds.has(p.post_id))
      .map((p) => ({
        id: p.post_id,
        title: p.title,
        url: p.url,
        role: p.role,
        traffic: p.traffic_90d,
        clusterId: p.cluster_id,
      }));

    const nodeMap = new Map(nodes.map((n) => [n.id, n]));

    const links: NetworkLink[] = filteredByCluster
      .filter((p) => nodeMap.has(p.post_a_id) && nodeMap.has(p.post_b_id))
      .map((p) => ({
        source: p.post_a_id,
        target: p.post_b_id,
        pairId: p.id,
        overlapScore: p.overlap_score,
        severity: p.severity,
      }));

    // Zoom behavior
    const g = svg.append('g');
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 5])
      .on('zoom', (event: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
        g.attr('transform', event.transform.toString());
      });
    svg.call(zoom);

    // Simulation
    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink<NetworkNode, NetworkLink>(links).id((d) => d.id).distance(120))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius((d) => radiusScale((d as NetworkNode).traffic) + 10));

    const maxTraffic = Math.max(...nodes.map((n) => n.traffic), 1);
    const radiusScale = (traffic: number) => 8 + (traffic / maxTraffic) * 24;

    // Links
    const linkElements = g
      .append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', (d) => SEVERITY_COLORS[d.severity])
      .attr('stroke-width', (d) => 1 + d.overlapScore * 4)
      .attr('stroke-opacity', 0.6)
      .style('cursor', 'pointer')
      .on('click', (_event: MouseEvent, d: NetworkLink) => {
        onSelectEdge(d.pairId);
      });

    // Nodes
    const nodesGroup = g.append('g');
    const nodeElements = nodes.map((node) => {
      const nodeG = nodesGroup.append('g')
        .datum(node)
        .style('cursor', 'pointer')
        .on('click', (_event: MouseEvent, d: NetworkNode) => {
          onSelectNode(d.id);
        });

      nodeG.call(
        d3.drag<SVGGElement, NetworkNode>()
          .on('start', (event) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            event.subject.fx = event.subject.x;
            event.subject.fy = event.subject.y;
          })
          .on('drag', (event) => {
            event.subject.fx = event.x;
            event.subject.fy = event.y;
          })
          .on('end', (event) => {
            if (!event.active) simulation.alphaTarget(0);
            event.subject.fx = null;
            event.subject.fy = null;
          })
      );

      return nodeG;
    });

    nodeElements.forEach((nodeG) => {
      const d = nodeG.datum();
      nodeG.append('circle')
        .attr('r', radiusScale(d.traffic))
        .attr('fill', ROLE_COLORS[d.role])
        .attr('fill-opacity', 0.8)
        .attr('stroke', ROLE_COLORS[d.role])
        .attr('stroke-width', 2);

      nodeG.append('text')
        .text(d.title.length > 30 ? `${d.title.slice(0, 27)}...` : d.title)
        .attr('dy', radiusScale(d.traffic) + 14)
        .attr('text-anchor', 'middle')
        .attr('fill', '#94a3b8')
        .attr('font-size', '10px');
    });

    // Tick
    simulation.on('tick', () => {
      linkElements
        .attr('x1', (d) => (d.source as NetworkNode).x ?? 0)
        .attr('y1', (d) => (d.source as NetworkNode).y ?? 0)
        .attr('x2', (d) => (d.target as NetworkNode).x ?? 0)
        .attr('y2', (d) => (d.target as NetworkNode).y ?? 0);

      nodeElements.forEach((nodeG) => {
        const d = nodeG.datum();
        nodeG.attr('transform', `translate(${d.x ?? 0},${d.y ?? 0})`);
      });
    });

    return () => {
      simulation.stop();
    };
  }, [posts, pairs, onSelectNode, onSelectEdge, severityFilter, clusterFilter]);

  useEffect(() => {
    const cleanup = buildGraph();
    return () => cleanup?.();
  }, [buildGraph]);

  return (
    <div ref={containerRef} className="h-full w-full">
      <svg ref={svgRef} className="h-full w-full" />
    </div>
  );
}
