using System;
using CodeAnalysisDebug.Interfaces;

namespace CodeAnalysisDebug.Infrastructure
{
    public class EmailNotificationSender : INotificationSender
    {
        public void Send(string destination, string subject, string body)
        {
            // In a real system this would use SMTP or a provider SDK.
            // For debug/indexing purposes, we just write to the console.
            Console.WriteLine($"[EMAIL] To={destination} Subject={subject}");
            Console.WriteLine(body);
        }
    }
}


