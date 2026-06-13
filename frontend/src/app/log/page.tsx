import Navbar from "@/components/Navbar";
import DailyLogForm from "@/components/DailyLogForm";

export default function LogPage() {
  return (
    <div>
      <Navbar />
      <main className="max-w-2xl mx-auto px-4 py-8 space-y-4">
        <div>
          <h1 className="text-2xl font-semibold mb-1">Daily Log</h1>
          <p className="text-gray-500 text-sm">Log today's metrics — weight, energy, water, and supplements.</p>
        </div>
        <DailyLogForm />
      </main>
    </div>
  );
}
