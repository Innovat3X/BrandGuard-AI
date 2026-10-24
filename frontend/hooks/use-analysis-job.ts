"use client";

import { useQuery } from "@tanstack/react-query";

import { getAnalysisJob } from "@/services/analysis.service";
import type { UUID } from "@/types/api-contracts";

const POLLING_INTERVAL = 3000;

export function useAnalysisJob(jobId?: UUID) {
  return useQuery({
    queryKey: ["analysis-job", jobId],

    queryFn: () => {
      if (!jobId) {
        throw new Error("Analysis job ID is required.");
      }

      return getAnalysisJob(jobId);
    },

    enabled: Boolean(jobId),

    refetchInterval: (query) => {
      const status = query.state.data?.status;

      // Continue checking while analysis is running.
      if (status === "queued" || status === "processing") {
        return POLLING_INTERVAL;
      }

      // Stop checking for completed, partial or failed jobs.
      return false;
    },

    refetchIntervalInBackground: false,
  });
}
