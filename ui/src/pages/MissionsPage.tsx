import PageHeader from "../components/layout/PageHeader";
import Card from "../components/shared/Card";

export default function MissionsPage() {
  return (
    <div>
      <PageHeader title="Missions" description="Define mission prompts and assign to drones." />
      <Card>
        <div className="text-sm text-gray-500 italic">
          Mission editor lands in Phase 3 (mission ontology object + create-mission action).
        </div>
      </Card>
    </div>
  );
}
