using System;

namespace CodeAnalysisDebug.Models
{
    public enum UserRole
    {
        Guest,
        Member,
        Admin
    }

    public class User
    {
        public Guid Id { get; }

        public string Email { get; }

        public string? DisplayName { get; set; }

        public UserRole Role { get; set; } = UserRole.Member;

        public DateTime CreatedAtUtc { get; }

        public User(string email)
        {
            Id = Guid.NewGuid();
            Email = email;
            CreatedAtUtc = DateTime.UtcNow;
        }

        public string GetContactLabel()
        {
            return string.IsNullOrWhiteSpace(DisplayName)
                ? Email
                : $"{DisplayName} <{Email}>";
        }
    }
}


