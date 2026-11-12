"use client";

import { AIProvidersManager } from "@/app/components/ai-providers-manager";

export default function SystemOwnerAIProvidersPage() {
  return (
    <div className="w-full p-6 sm:p-8">
      <AIProvidersManager scope="platform" />
    </div>
  );
}
