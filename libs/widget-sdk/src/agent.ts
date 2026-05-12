/**
 * @platform/widget-sdk — Agent skill plugin contracts
 *
 * An agent skill plugin bundles:
 *   1. A Python MCP tool definition (lives at the path given by manifestPath,
 *      registered by libs/mcp-server via plugin auto-discovery)
 *   2. An optional Vue component that renders the tool's result inline in
 *      the agent chat or sidebar
 *
 * The Python side:
 *   Each plugin directory under libs/mcp-server/finetune_mcp/plugins/
 *   should export TOOLS: list[dict] following the MCP tool schema.
 *   The loader reads TOOLS from each file and merges them into the server.
 *
 * The frontend side:
 *   The result component receives AgentSkillResultProps and renders the
 *   tool call result in whatever format makes sense.
 */

import type { Component } from "vue";

export type AgentSkillSurface = "classify" | "dataset" | "preview" | "global";

export interface AgentSkillDescriptor {
  /**
   * Must match the Python MCP tool name exactly.
   * Used to route tool call results to the correct renderer.
   */
  toolName: string;
  /** Human-readable name shown in skill listings. */
  displayName: string;
  description: string;
  /** Which app surfaces expose this skill to the agent. */
  surfaces: AgentSkillSurface[];
  /**
   * Optional Vue component that renders the tool's structured result.
   * If absent, the agent chat renders the result as plain text / markdown.
   */
  resultComponent?: Component;
}

/**
 * Props passed to a skill result component.
 */
export interface AgentSkillResultProps {
  /** The raw result returned by the MCP tool call. */
  result: unknown;
  /** Tool name (same as AgentSkillDescriptor.toolName). */
  toolName: string;
  /** Surface the skill was invoked from. */
  surface: AgentSkillSurface;
}

export function defineAgentSkill(
  descriptor: AgentSkillDescriptor,
): AgentSkillDescriptor {
  if (!descriptor.toolName || descriptor.toolName.trim() === "") {
    throw new Error("[widget-sdk] defineAgentSkill: toolName must not be empty");
  }
  if (!descriptor.displayName || descriptor.displayName.trim() === "") {
    throw new Error(
      `[widget-sdk] defineAgentSkill(${descriptor.toolName}): displayName must not be empty`,
    );
  }
  if (descriptor.surfaces.length === 0) {
    throw new Error(
      `[widget-sdk] defineAgentSkill(${descriptor.toolName}): surfaces must not be empty`,
    );
  }
  return descriptor;
}
