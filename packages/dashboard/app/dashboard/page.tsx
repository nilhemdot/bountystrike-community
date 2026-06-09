import FindingsPipeline from "./components/FindingsPipeline";
import ProgramRanking from "./components/ProgramRanking";
import ApprovalQueue from "./components/ApprovalQueue";
import AgentActivityFeed from "./components/AgentActivityFeed";
import KillSwitch from "./components/KillSwitch";
import EvidenceAuditTrail from "./components/EvidenceAuditTrail";
import StatsBar from "./components/StatsBar";
import Header from "./components/Header";

export default function DashboardPage() {
  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Header />
      <StatsBar />

      {/* Main grid — fixed height, internal panels scroll independently */}
      <main className="flex-1 overflow-hidden p-3">
        {/* Large screen: 4-col grid, 2 rows each ~50% height */}
        <div className="hidden xl:grid xl:grid-cols-4 xl:grid-rows-2 gap-3 h-full">
          {/* Col 1: Findings Pipeline — full height */}
          <div className="row-span-2 min-h-0">
            <FindingsPipeline className="h-full" />
          </div>
          {/* Col 2 row 1: Program Ranking */}
          <div className="min-h-0">
            <ProgramRanking className="h-full" />
          </div>
          {/* Col 2 row 2: Agent Activity Feed */}
          <div className="min-h-0">
            <AgentActivityFeed className="h-full" />
          </div>
          {/* Col 3 row 1: Approval Queue */}
          <div className="min-h-0">
            <ApprovalQueue className="h-full" />
          </div>
          {/* Col 3 row 2: Evidence Audit Trail */}
          <div className="min-h-0">
            <EvidenceAuditTrail className="h-full" />
          </div>
          {/* Col 4: Kill Switch — full height */}
          <div className="row-span-2 min-h-0">
            <KillSwitch className="h-full" />
          </div>
        </div>

        {/* Medium screen: 2-col stacked */}
        <div className="hidden lg:grid xl:hidden lg:grid-cols-2 gap-3 h-full overflow-auto">
          <div className="min-h-[460px]"><FindingsPipeline className="h-full" /></div>
          <div className="min-h-[460px]"><KillSwitch className="h-full" /></div>
          <div className="min-h-[380px]"><ProgramRanking className="h-full" /></div>
          <div className="min-h-[380px]"><ApprovalQueue className="h-full" /></div>
          <div className="min-h-[380px]"><AgentActivityFeed className="h-full" /></div>
          <div className="min-h-[380px]"><EvidenceAuditTrail className="h-full" /></div>
        </div>

        {/* Mobile: single column */}
        <div className="lg:hidden flex flex-col gap-3 overflow-auto pb-4">
          <div className="min-h-[480px]"><FindingsPipeline className="h-full" /></div>
          <div className="min-h-[380px]"><ProgramRanking className="h-full" /></div>
          <div className="min-h-[380px]"><ApprovalQueue className="h-full" /></div>
          <div className="min-h-[380px]"><AgentActivityFeed className="h-full" /></div>
          <div className="min-h-[380px]"><KillSwitch className="h-full" /></div>
          <div className="min-h-[380px]"><EvidenceAuditTrail className="h-full" /></div>
        </div>
      </main>
    </div>
  );
}
