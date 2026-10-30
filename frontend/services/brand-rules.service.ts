import { apiRequest } from "@/lib/api-client";

export type BrandRuleCategory = "tone" | "terminology" | "messaging" | "other";
export type BrandRuleSeverity = "info" | "low" | "medium" | "high";
export type BrandKnowledgeStatus = "draft" | "approved" | "archived";

export interface BrandRuleVersion {
  id: string;
  version_number: number;
  category: BrandRuleCategory;
  description: string | null;
  rule_text: string;
  severity: BrandRuleSeverity;
  status: BrandKnowledgeStatus;
  effective_from: string | null;
  created_by: string;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
}

export interface BrandRule {
  id: string;
  title: string;
  created_at: string;
  versions: BrandRuleVersion[];
}

export interface BrandRulesListResponse {
  items: BrandRule[];
}

export interface BrandRuleDraftInput {
  title: string;
  category: BrandRuleCategory;
  description?: string | null;
  rule_text: string;
  severity: BrandRuleSeverity;
}

export interface BrandRuleVersionInput {
  category: BrandRuleCategory;
  description?: string | null;
  rule_text: string;
  severity: BrandRuleSeverity;
  effective_from?: string | null;
}

const RULES_PATH = "/api/v1/brand/rules";

export async function listBrandRules(): Promise<BrandRule[]> {
  const response = await apiRequest<BrandRulesListResponse>(`${RULES_PATH}?limit=100`);
  return response.items;
}

export async function createBrandRule(input: BrandRuleDraftInput): Promise<BrandRule> {
  return apiRequest<BrandRule>(RULES_PATH, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateBrandRule(
  ruleId: string,
  input: BrandRuleDraftInput,
): Promise<BrandRule> {
  return apiRequest<BrandRule>(`${RULES_PATH}/${encodeURIComponent(ruleId)}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export async function createBrandRuleVersion(
  ruleId: string,
  input: BrandRuleVersionInput,
): Promise<BrandRule> {
  return apiRequest<BrandRule>(
    `${RULES_PATH}/${encodeURIComponent(ruleId)}/versions`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function approveBrandRule(ruleId: string): Promise<BrandRule> {
  return apiRequest<BrandRule>(
    `${RULES_PATH}/${encodeURIComponent(ruleId)}/approve`,
    { method: "POST" },
  );
}
