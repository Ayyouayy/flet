import flet as ft


def main(page: ft.Page):
    page.add(
        ft.SafeArea(
            ft.Container(
                ft.Text("This app is run by Flet CLI"),
                alignment=ft.alignment.center,
            ),
            expand=True,
        )
    )


ft.app(main)
