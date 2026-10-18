import PageStub from "../components/PageStub";

export default function OperationsPage() {
  return (
    <PageStub
      breadcrumb="Operations"
      title="Operator insights"
      summary="Composition shifts, missed recovery, and bin workload for the facility."
      sections={[
        { title: "Streams", body: "What the facility sees, ranked by volume." },
        { title: "Missed recovery", body: "Items routed to landfill that could have been recycled or composted." },
        { title: "Workflow", body: "Peak windows, bin-fill cadence, and placement recommendations." },
      ]}
    />
  );
}
