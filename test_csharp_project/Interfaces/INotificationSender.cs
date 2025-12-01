namespace CodeAnalysisDebug.Interfaces
{
    public interface INotificationSender
    {
        void Send(string destination, string subject, string body);
    }
}


