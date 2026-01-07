{ pkgs, ... }:

{
  languages.python = {
    enable = true;
    package = pkgs.python3;

    venv = {
      enable = true;
      # Concatenate requirements.txt and requirements-dev.txt into a single file
      requirements = builtins.concatStringsSep "\n" [
        (builtins.readFile ./requirements.txt)
      ];
    };
  };
}
