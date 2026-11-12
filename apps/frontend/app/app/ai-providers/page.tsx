"use client";

import { AIProvidersManager } from "@/app/components/ai-providers-manager";

export default function AIProvidersPage() {
  return (
    <div className="p-4 sm:p-6 md:p-8">
      <AIProvidersManager scope="organization" />
    </div>
  );
}
