import Navbar from "@/components/Navbar";
import ChatWindow from "@/components/ChatWindow";

export default function ChatPage() {
  return (
    <div className="flex flex-col h-screen">
      <Navbar />
      <div className="flex-1 overflow-hidden">
        <ChatWindow />
      </div>
    </div>
  );
}
