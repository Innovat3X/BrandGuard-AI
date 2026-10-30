import { apiRequest } from "@/lib/api-client";

export type FactKey =
  | "product_price"
  | "discount_percentage"
  | "warranty_duration"
  | "battery_life_duration"
  | "product_weight"
  | "product_capacity";

export type FactKind = "currency" | "percentage" | "duration" | "quantity";
export type BrandKnowledgeStatus = "draft" | "approved" | "archived";

export interface StructuredFactValue {
  kind: FactKind;
  value: string;
  unit: string;
}

export interface BrandFactVersion {
  id: string;
  version_number: number;
  fact_text: string;
  source_url: string | null;
  fact_key: FactKey | null;
  structured_value: StructuredFactValue | null;
  status: BrandKnowledgeStatus;
  effective_from: string | null;
  expires_at: string | null;
  created_by: string;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
}

export interface BrandFact {
  id: string;
  label: string;
  created_at: string;
  versions: BrandFactVersion[];
}

export interface BrandFactsListResponse {
  items: BrandFact[];
}

export interface BrandFactDraftInput {
  label: string;
  fact_text: string;
  source_url?: string | null;
  fact_key?: FactKey | null;
  structured_value?: StructuredFactValue | null;
  effective_from?: string | null;
  expires_at?: string | null;
}

export interface BrandFactVersionInput {
  fact_text: string;
  source_url?: string | null;
  fact_key?: FactKey | null;
  structured_value?: StructuredFactValue | null;
  effective_from?: string | null;
  expires_at?: string | null;
}

const FACTS_PATH = "/api/v1/brand/facts";

export async function listBrandFacts(): Promise<BrandFact[]> {
  const response = await apiRequest<BrandFactsListResponse>(`${FACTS_PATH}?limit=100`);
  return response.items;
}

export async function createBrandFact(input: BrandFactDraftInput): Promise<BrandFact> {
  return apiRequest<BrandFact>(FACTS_PATH, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateBrandFact(
  factId: string,
  input: BrandFactDraftInput,
): Promise<BrandFact> {
  return apiRequest<BrandFact>(`${FACTS_PATH}/${encodeURIComponent(factId)}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export async function createBrandFactVersion(
  factId: string,
  input: BrandFactVersionInput,
): Promise<BrandFact> {
  return apiRequest<BrandFact>(
    `${FACTS_PATH}/${encodeURIComponent(factId)}/versions`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export async function approveBrandFact(factId: string): Promise<BrandFact> {
  return apiRequest<BrandFact>(
    `${FACTS_PATH}/${encodeURIComponent(factId)}/approve`,
    { method: "POST" },
  );
}
